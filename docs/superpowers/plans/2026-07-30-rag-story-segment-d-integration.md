# 线程 D：剧情 Segment 前置门、集成与向量影子构建 Implementation Plan

> **当前执行依据：** 第 6.5 项已验收，当前合法恢复点为 E 干净 `09fe8836c6c3df85489d288b1e72ea695914dfe4`。现在仅执行下方第 6.6 项的只读核定，不重测已验收批。2026-09-05 修订规定共同边界；下方各已验收批的旧起点、RED-only、Step 6/Build A、`c81d336 + 11 dirty` 都不是当前恢复条件。保持 `D → 一个受监督的 E worker` 两层，不重新启动 C、D0 或新 E 会话。

### 2026-09-10 第 6.6 项：通道 Recall 与融合排序，先只读核定

- 同一 E 在干净 `09fe883` 核对 `atom_bm25_recall_at_80`、`segment_dense_recall_at_30`、`fused_mrr_at_8`、`fused_ndcg_at_8` 四门。复用已保存的真实通道/融合排名、独立 gold 及既有 Atom→Segment 闭包；先明确子集、完整分母、实际每 KB Top-K 与多分支作用域、rank/gain/IDCG 计算、实际空结果和缺测的区别，不重做检索/排序/packing。
- D 同步核对冻结 baseline/equivalence 的阶段和排名身份。BM25 要求不低于独立 baseline，MRR/nDCG 要求不低于 baseline−0.02；历史 RRF/final-context 不能冒充 raw BM25，Segment 与历史 Child/Parent 排名不能无说明混比。分别报告可复用的真实控制、缺失的控制、五个状态例不可比和必要的后续生产阶段，不填零、不用 candidate 自比、不重开 D0 或擅自重采集。
- 只回一份短报告，列已有字段/函数、最小连贯实现范围和确实需要 D 定案的语义；无代码/文档修改、stage/commit、测试/采集/全量/外部调用或新文件/任务。D 定案后才放行实施，不凭这轮报告把四门标完成；保持既有阈值/gold/schema、同一 E 与 Astra/xhigh/标准速度。

### 2026-09-10 当前检查点：第 6.5 项已验收

- D 已在 E 原分支提交 `09fe8836c6c3df85489d288b1e72ea695914dfe4`（parent `1ca7f77`）。仅 `src/rag_eval/story_run_observations.py` 与 `tests/test_story_segment_eval.py`，`+311/-1`：既有评测消费者净 +135 行、测试净 +175 行；无运行时代码、schema、冻结输入或新文件变化。两文件提交前后 SHA 一致，E 树/index 干净，未合并 main。
- E 有效 RED **2 failed**（40.29 秒），OS temp `s65red-63b61b07.log`，SHA `6207fde09f0b468b3bfa2e9a30ea80f103a3b511e518de0987d917f41c1ce49a`；最终受影响 **8 passed**（131.79 秒），`s65green-16efee77.log`，SHA `ecd8448a254d64cbdfe3556068cea264da2a86f7cabc633d155d4c67cc6a9314`。邻接原为 **37 passed / 1 failed**，唯一失败是旧 group-recall 测试未将已验收 6.4 三门及本批两门移出 missing 清单；迁移到 20/36 并补实际分母/调用断言后，该节点 **1 passed**（33.66 秒），`s65adjfix-1617a91b.log`，SHA `880f081e80d43f521bdeeb8bbb64405b71273839e8bea272c2d5194d7f62365c`。未改产品来兼容旧断言，不把这些重叠覆盖相加或称为一次全绿。
- D 独立真实执行/分支证据节点 **6 passed**（44.08 秒），OS temp `1999wiki-d-s65-e0237858016949e1876da043a68ebfc7/pytest.log`，SHA `e79142d037b931ef4a008b0b2c2566432301775dfee8ff7d192b3df6a860f705`。复用已固定 6.4 小观测（SHA `1d34064a88386cf65dd3a1af7c1c63d6a0692d7ee22e3fffcc1c066dc548a315`），通过 **14 项冷评分检查**：独立错 Owner/空金标/错 origin、重复镜像、错 scope、漏 mention、缺 target/assignment/context、生成失败和 warmup 隔离；先验证原观测，变异仅隔离评分逻辑，不宣称变异仍是合法 wire 事务。日志同目录 `cold-final.log`，SHA `abd6decb9b27d26de463d283792f674be12f2eba84a4a95f03f6aa1d2669f1f2`；执行/normalizer/socket 禁用、输入零漂移。D 另逐字段对照 6.4/6.5 的 current、historical、stateful 三份报告，各自其余 54 个指标完全一致，均 `no_go`。
- 两个本地 producer 已完成，累计 **20 项、36 项仍待完成**，不表示真实题集正确率已通过。独立 gold 的完整单位、额外错误声明和缺测语义保留；未新增防御框架或运行时检查。没有真实全量/embedding/Milvus/SSH/媒体/激活，最终质量、HTTP/TTFT、状态历史控制和 E 最终交付仍未完成。普通下一批核定由 D 负责，无需用户再批准日常交接；当前未自动放行新批次。

### 2026-09-10 前序检查点：第 6.4 项已验收

- D 已在原 E 分支提交 `1ca7f77b96c360e427618d899ba32f90744c152a`（parent `cf1ff72`），仅本批 16 个既有文件 `+576/-57`，生产净 +206 行、测试净 +313 行，无新模块或监督文件。提交前后逐文件 SHA 一致，E 树/index 干净；未合并 main，冻结题集/阈值/Spec、公开接口文件及 main 用户原有脏文件不变。
- 三门现从同次执行的实际 Detector、SDK 公开 HTTP request hook、reranker `urlopen` 尝试派生逐单位计数；完整请求/KB 观测区间与实际 hook 可观测性区分零次和缺测。其他 53 门算法、原九字段指标行和调用/重试策略不改。纯非 Story Child 曾因复用 Story session 改变异常类型，有效 RED 后已撤回该复用，只透传原调用的 trace/身份，保持原成功结果与异常类型。
- E 基础受影响回归 **65 passed**（234.23 秒，OS temp `s64focused-88f0c0eb.log`，SHA `e567f2c148b171d13dae7a8252fd62b623bde6cdaada961918327c71a4306bbb`），邻接 **24 passed**，collect→冷消费 **2 passed**。D 发现的 P1 是成功 adapter 缺 API 事件被错误计为零次；修复只关联同 KB/query/model、adapter 区间内已有 API 事件，缺失仍缺测，不伪造次数。对应 RED **1 failed**（`s64p1red-e112dcf5.log`，SHA `464f1fcbb448eeed233da171af3377f8cb2202448a9996e293a68af97c250907`），GREEN **1 passed**（`s64p1green-71d51eaf.log`，SHA `57348fbb1f64720ec5c81151cee829e55610b22761fb6857562d456dbd49d10b`），最终受影响 **13 passed**（`s64p1adj-0c936ff9.log`，SHA `5c9a2156b8b4418e191298f2f402a8eb0602725e9223f6d63ec103801f87960b`）。复用未变覆盖，不累加重叠测试数。
- D 独立五文件邻接 **271 passed**（13.28 秒），日志 OS temp `1999wiki-d-s64-adj-3386e35deb35493c92711847bb340cee/pytest.log`，SHA `16dbeec2bbc907d07aabf292f64a02201e1597bebcc8a651f526662e08171f88`。另复用固定小 fixture（SHA `1d34064a88386cf65dd3a1af7c1c63d6a0692d7ee22e3fffcc1c066dc548a315`）完成 **11 项冷复验**：原计数、重复 API、缺 API/KB/hook/request、身份/时间关联漂移、HTTP 前失败及无 adapter；真实零次保留，缺测不通过。日志同目录 `cold-final.log`，SHA `4e9cfa9cf8aae8a9c85fddbcc92966c9f50f98db13dd72c939bd42b4286f9bd7`；执行入口、normalizer 与 socket 禁用，未再采集，输入字节不变。上述日志及最终 16 文件在提交前再次核对一致，未重复运行未变测试。
- 本批增加三个本地 producer，累计 **18 项已有本地 producer、38 项待完成**，不是 18 项真实质量门已通过。HTTP/TTFT、五条状态例历史控制和真实题集仍未完成，整体 `no_go`。没有真实 embedding/Milvus/SSH/媒体/激活。下批尚未下发，由 D 在既有 S3 内先核定范围，不要求用户重新批准普通验收，不自动进入 S4/S5 或真实构建。

### 2026-09-10 第 6.5 项历史实施范围：归属与授权指标（已验收）

**只读核定已完成，现放行两门最小实现：** E 只读轮 `01a0891e-49b7-78a1-a545-c4957725b7eb` 与 D 独立核对一致：冻结 v2 有 157 个 Story mention span（74 例），正例授权基数为 86 个 query–Owner 单位（direct 83、continuation 1、anchor 2）。70 个 direct 正例的 83 个标注 span 与 83 个有序 Owner 逐例同基数且 Owner 不重复；所有 span 与原问题位置/文本相符。这些数值只是当前输入的复核结果，实现须动态计算。现有 v4 已有 final plan、detection/assignment、授权 context 与状态来源，不新增运行时字段。

- **唯一归属：** 阈值的 `all_unique_source_spans` 按 Spec `REQUESTPLAN2-P0-04/09` 与第 26.1 节解释为有独立金标的 Story mention occurrence，不是完整子任务 span 数。以 `(query_id, start, end)` 为单位保留 157 个基数；同 Owner 不同位置不合并。将金标位置/文本关联实际 occurrence，再独立按最终 subtask 的 span 检查恰好一个 ready KB 或合法 boundary 归属，并核对 assignment 行；不能以 validator/assignment_closed 成功代替检查，不能将同一 subtask 的两个 span 计作两个 Owner。分页待续与 33+ 拒绝仍计其原问题 occurrence；continuation 携带的旧 Plan/setup 不新增本次跨度，当前 anchor/open-domain 无标注时也不添单位。检测漏掉已有金标应计失败，不缩分母；完整必要观测缺失仍缺测。
- **授权正确性：** 保留每个冻结预期 query–Owner 单位，不按实际成功、非空检索或已授权集合筛选。direct 使用金标 span 与有序 Owner 的独立对应确定授权所在 scope；continuation 只用实际 target 页，anchor 只用实际 target 已提交来源。逐单位检查 expected Owner/order/origin/coverage、实际 required/authorized 同一 context 及其唯一作用域；错误 origin/顺序/归属不能仅靠 Owner 集合相同通过。`answer-scope-06` 的预期检索失败不移除其授权单位，授权与答案/引用成功分开。
- **额外声明不能逃出分母：** 86 是正例基数，不是排除错误授权的固定总分母。额外 Owner、重复消费同一应有授权 scope 的声明作为分子零的失败单位加入分母；同一 context 内 required/authorized 对同一声明的镜像只计一次，保留重复次数，不用集合去重掩盖。不得笼统禁止同 Owner 的不同合法 occurrence scope；只有对同一金标 scope 的重复/错分支声明属于重复错误。当前金标为空的分页待续、33+ 拒绝、anchor clear 和 open-domain 仍检查 actual required/authorized 为空；open-domain 检索返回 Story 不等于 required 授权。错误 Owner 导致原金标未满足且多出声明时，两项事实均保留。该口径落实原零容忍授权精确率，不改 gate 名称、阈值文件、gold 或公开字段。
- **现有消费者接线：** 仅 candidate 首个 timed target，setup/warmup/其他重复样本不计。复用 `_execution_planning` 和已验证输入；接口/身份严格校验与独立 gold 评分分工，不复制运行时授权/Detector/Finalizer，不重跑它们来算期望。所有可能产生额外授权的目标都须有完整观测；缺目标不可按零声明通过。精确已证明的协议拒绝无 plan/授权单位且下游为零，不伪造 planning；沿已批准拒绝语义处理。报告沿原 56 行九字段、query diagnostics、缺测/零分母规则，另 54 门行为保持；不另建 scorer、receipt、sidecar、版本兼容或采集入口。
- **唯一文件范围与验证：** 仅 E 的 `src/rag_eval/story_run_observations.py` 与 `tests/test_story_segment_eval.py`。在既有小 fixture/节点做有效 RED→最小实现→GREEN：不同位置同 Owner、同任务多 span、零/多归属、合法 boundary、漏检测不缩分母；完整授权与同集合错顺序/错 origin/错 scope、额外/重复授权、空金标错误授权、合法续页/anchor、检索失败仍计授权、缺 target/必要观测、协议拒绝和 setup 隔离。保留原生产者对照与所有显式负例，collect→冷消费者在禁止业务/normalizer/网络时可消费；不新增运行时防御逻辑。复用未变回归，跑受影响节点与必要 eval/baseline 邻接，不重跑全量构建链。Conda `1999wiki`、OS temp 日志/basetemp，报告改动量、未测项与日志。E 不 stage/commit、不写新文档/文件、不运行真实全量或外部服务；完成后 D 独立验收提交，不自行进入下一批。

- **恢复说明：** E 实施轮 `01a08941-3a78-7b83-a39f-c4d89143437e` 在上下文压缩后重新采用旧 `c81d336 + 11 dirty` 门禁，只预检即停止，未编辑或测试。D 已确认当前 HEAD/干净树正是已验收 6.4 的状态，不存在产品或冻结输入漂移；该历史状态阻断无效，继续本项，不重做 D2/旧 Step 6。此说明不豁免当前文件范围、冻结输入和实际测试要求。模型/思考等级保持 `gpt-6-astra / xhigh`、标准速度；本地 `service_tier=default` 已核对，任务接口不暴露单轮 tier，不声称已独立确认覆盖值。

### 2026-09-10 前序检查点：第 6.3 项已验收

- D 已在原 E 分支提交 `cf1ff72bc663d9946ccf5204e97c97568a616256`（parent `737b6aa`），四个既有文件 `+106/-25`，生产净 +8 行、测试净 +73 行，无新文件或监督层；树/index 干净，未合并 main。回答异常在原私有 answer 边界保留已完成的路由/outcome/scope，仍为失败且无引用/实体锚点；契约异常、真正检索失败和早期失败沿原处理。消费者删除旧失败状态兼容例外，并发观测测试按 subtask ID 关联。
- 有效 RED **4 failed / 4 passed**（73.68 秒），OS temp `s63red-91e70631.log`，SHA `146bd825474f1c2a6dfbf7d903de1a7728e22b6fc7206c2a86ca8737630d8157`。冻结后受影响 **15 passed**（133.80 秒），`s63green-f75fc46d.log`，SHA `fa229091c9367742646abf048c23e517937b244306f3b813fef0a9e18e2fb36d`；唯一 collect→冷消费者节点 **1 passed**（73.18 秒），`s63cold-ced97e7c.log`，SHA `e6bc581dc77605bbc1b82254f04ef7873dfc2eec161a68ef235fe1eda06d356d`。不将 RED 或重叠覆盖累加。
- D 独立旧执行/复合及 API/SSE 邻接 **50 passed**（3.68 秒），日志 OS temp `1999wiki-d-s63-adj-29ff7dfd6fcb4edd86738f6ff709b7e6/pytest.log`，SHA `fc5c559156bcd3a1311a303b57158b045803e4d18392424088e7a084d84d2f6e`。另复用已固定 v4 小 fixture（SHA `245d987d955e0bdcc00eb62b889b69425bd8279b6af18864d25ecbe0a046a097`），冷评分拒绝 public failed/outcome 篡改，缺失正常化记录仍缺测，原 `[1,2,2,4]` 分母及输入字节不变；禁用 normalizer 与网络，未再采集。生产 SHA 前后为 `266e9f5c584d0be87d885a4e2bc96f034808d297b0fa5ce4fe7fb4c57d13dd98` / `9e010b750c80912dc085459290b55e944f300a420d9a04808dba6207723c6de5`；冻结输入、接口和 main 用户脏文件不变。
- 本批只修复已暴露的真实根因，不新增指标 producer。仍为 15 项有本地 producer、41 项待完成、整体 `no_go`；没有真实题集/embedding/Milvus/SSH/媒体/激活。不把局部回归称为最终交付。

**第 6.4 项只读核定已完成：** 同一 E 在干净 `cf1ff72` 给出三门报告，D 已对实际入口和冻结阈值交叉核对，无需重复盘点。普通/anchor 的 Detector 调用在 `request_plan.py::RequestPlanFinalizer.finalize`，合法续页在 `story_authorization.py::authorize_story_continuation_action`，两者尚缺实际尝试观测；现有检测回执不是调用次数。共享 Story Dense session 已记录含失败的 adapter 尝试，但纯非 Story typed Child 的直接 `embed_query` 缺同型观测与 KB 绑定；现有事件不证明 SDK 内部 HTTP 重试数。`reranker.py::SiliconFlowRerankClient.score` 的 `urlopen` 尚缺请求尝试观测，外层 rerank 阶段或配置关闭不能独自证明 API 零调用。

D 已核定三门的计分边界，实施许可仅见下方 6.4 范围：在现有 `evaluate_hard_gates` 内仅为这三个调用门消费逐单位实际计数，其他门保留原四字段输入；仍输出原九字段指标行，不另建 scorer 或报告。单位来自原冻结请求/最终目标 KB 清单，而非出现过调用的子集；`numerator` 为实际调用总数、`denominator` 为完整单位数、`candidate` 为单位实际最大值，同时逐单位检查全部既有上下界。因而 `0/2` 或 `0/1` 不能靠汇总通过 Detector 门。Dense 另逐 KB 验证相同 query/model 的重复尝试数为零；实际两次重复仍报告两次并判失败，不伪造第三次调用。逐单位依据在既有 query diagnostics 中可追溯；未完整观测或零分母保持缺测/不通过，不从配置关闭或缺少 span 推出零次。

调用观测仍沿原 trace 与 setup/target 分离，成功和异常尝试均计入；协议拒绝沿既定口径，不造业务响应或改分母。Spec `PIPE-P0-07` 的 query embedding API 次数不得由 `embed_query` adapter 次数冒充，也不能为凑门修改重试策略或阈值。D 已核定实际 API 接点：在既有 `embeddings.py` 工厂通过 SDK 的 `DefaultHttpxClient` 和公开 request hook 观测每次 HTTP dispatch 尝试，保留 SDK 连接/超时/重试默认值；不改 SDK 私有方法、不全局 monkeypatch、不另建 transport/retry 框架。仅在 query embedding 调用动态范围内用私有 `ContextVar` 绑定原 trace 及 subtask/query/model 哈希，结束时 reset；不读取或落盘请求正文、密钥、URL，不把同步 query 接线扩成新的异步业务或文档构建功能。

D 在 Conda `1999wiki`（Python 3.11.15；openai 2.44.0、httpx 0.28.1、langchain-openai 1.3.3）用内存 MockTransport 且禁止 socket 外连验证：429 重试、超时重试、307 跳转三个并发场景均为一次 SDK 调用、两次 transport 尝试及两条正确绑定的 hook 记录，绑定退出后清空；未关闭 SDK 默认两次重试。这里只证明扩展点可用，不是产品 RED/GREEN、真实 API/性能证据或任何 gate 通过。缺 hook、缺请求/KB 完整观测仍不能记实测零。6.4 的合法起点为 E 干净 `cf1ff72`；三门和整体 `no_go` 尚未改变。

### 2026-09-10 第 6.4 项：同次执行的三个调用门

本批属于已批准的 S3 观测补齐，不进入 S4/S5 或新的产品阶段。D 仅放行 `request_detector_calls`、`dense_embedding_calls_per_knowledge_subtask`、`reranker_api_calls` 的有效 RED→最小实现→GREEN；不同时补其他待测门、改调用策略或重新调查已核定接点。完成后由 D 独立验收提交，E 不 stage/commit、不自行进入下一批。

- **实际尝试入口：** Detector 的普通/anchor finalizer 与合法 continuation 路各在实际 `detect` 调用处记录尝试，不把 finalizer 完成或已有 detection receipt 当次数。Dense 复用上述公开 HTTP hook，原共享 session 的 adapter span 保留为逻辑调用/耗时，不和 API attempt 混算；纯非 Story typed Child 也绑定目标 KB/query/model，不能只覆盖 Story。Reranker 在现有 `SiliconFlowRerankClient.score` 的实际 `urlopen` 边界计尝试，原外层 rerank span 仍只是阶段；开关继续关闭。观测只透传既有 trace，不增加业务调用、重试、向量重算或第二份计数器。
- **完整观测与零次：** collector 用原 `RequestTrace` 包住实际目标执行至返回或异常退出；每个目标 KB 的检索区间也须有真实结束依据，异常不可丢事件。客户端可观测性来自实际已安装 hook 的检查，不能预填 true、以配置关闭代替或给无观测 fake client 伪造 API 零次。新增记录优先使用现有 span/安全标量，不新建 observer、receipt、snapshot 字段或完整输入镜像。`NullTrace`、缺 frame/缺 hook、未闭合执行和未知目标集保持对应门缺测；完整执行但实测零次是计分事实，不得当缺测来掩盖 Detector 失败。
- **原语义不变：** setup、warmup 与 candidate 首个 timed target 沿原隔离；续页只计实际目标，不重计 setup 或未执行兄弟。协议拒绝仍只证明原解码拒绝，不生成 plan/packet/Detector 调用；如增加外层观测 span，既有拒绝识别仅精确接受这个外层与原解码异常，不能顺带放宽异常分类。生成失败后已完成的检索状态/scope 保持 6.3 行为；异常传播、授权、会话提交和公开 REST/SSE 不改。
- **计分与冷消费：** 按上方逐单位规则在原 consumer/runner 一次派生计数；完整分母不按有调用、成功或非空结果筛选。缺单位事实的汇总输入不能自报通过；只新增这三门需要的内部逐单位输入，其他门算式/字段保持。沿原 trace 和 query diagnostics/性能报告展示实际计数、逻辑 adapter 耗时与缺测状态，不能把 hook 记录耗时当 HTTP 总延迟或 TTFT。冷 evaluate/performance 不执行业务、normalizer、SDK 或网络；不改 frozen gold/threshold/baseline，不自动迁移旧观测。
- **生产 allowlist：** `src/rag/{tracing,embeddings,vectorstore,story_retrieval,request_plan,story_authorization,chain,execution,retriever,reranker}.py` 与 `src/rag_eval/{story_run_observations,story_segment_runner}.py`。仅作上述观测/透传/消费；不改各自业务决策算法、客户端重试/代理/连接默认行为、公开响应模型或依赖版本。尽量使用既有参数/入口，不为未触发的假设故障扩充防御分支。若无法在现有 span/报告结构内表达必要事实，先给 D 精确缺口，不自行增加版本兼容层。
- **测试 allowlist 与退出：** 仅现有 `tests/{test_tracing,test_rag_tracing,test_reranker,test_story_request_plan_v2,test_story_authorization,test_story_segment_runtime,test_story_segment_eval}.py`，无新文件。另精确允许 `tests/test_retriever.py::_RecordingReranker.rerank` 增加可选 keyword-only `trace=None`，函数体/limit 记录及既有断言不变，并回归 `test_huiji_multi_intent_allocates_exact_skill_and_clamped_voice_coverage`；不为旧 spy 增加产品 type/hasattr/重试兼容。RED 须暴露真实缺失/错误计数，不仅测试导入失败：Detector 的逐请求 `0/1`、`0/2` 不可被平均或最大值掩盖；Dense 同 query 两次、不同 query 三次、失败重试及并发绑定；reranker 零/一次异常尝试；缺 hook/frame 与实测零的区别。用安装后的真实本地小 fixture 走 collect→冷消费者，同时验证协议拒绝、非 Story KB、续页 setup 隔离与 6.3 生成失败不退化。HTTP 使用现有 SDK 加内存 MockTransport/本地替身并禁止外连，不是真实 API。复用未变回归，不重跑全量构建链；Conda `1999wiki`、OS temp 日志/basetemp。报告实际改动量、RED/GREEN、未测项与日志，不新建监督文件；局部 producer 完成不等于真实质量通过或整体 go。

### 2026-09-10 前序检查点：第 6.2 项观测实现已验收

- D 已在原 E 分支提交 `737b6aa1f3ca449e407bd764ba64b355f729acd0`（parent `7372d8c`），九文件 `+574/-64`，生产净 +209 行（runtime/backend 净 +5、现有 evaluator 净 +204），测试净 +301。没有新文件、runner、公开 schema 镜像、监督回执或新的产品规则引擎；E 树/index 干净，尚未合并 main。
- 同次业务首次正常化实参/结果在生成前保存，collector 对同一实参实际再调用一次，冷消费者不调用 normalizer。正式 REST 与 staged SSE 共用实际投影函数；观测格式为 `observations/v4`，历史观测不自动迁移，性能报告仍 v2，HTTP/TTFT 仍未测。Scope oracle 与运行时决策 helper 独立，未知严格姿态不猜通过。
- D 曾复现配套篡改：保留实际非空 selection/context，却把 scope final units 清空并同步改两次结果，四门仍为 1.0。该 P1 现已通过有序 unit 摘要/分配身份、状态及 first/public 关联关闭；LLM 后删除正常化记录保持缺测。修复中重复的正文 citation-marker 解析和 Retriever shortfall 归因重推已移除，正文/引用完整性继续由既有门负责。最终 consumer SHA `d168c2b6010991bc7297074985f98e9d2e6fe24e9f57d5d547fda63641837220`。
- 基础 RED **4 failed**（17.93 秒），OS temp `s62red-8b548b76.log`，SHA `479e9ae1e92bf81b8baea534fbd95a38bcba10806fe00a25d1188e743b9991cb`；P1 RED **2 failed**（27.29 秒），`s62p1red-a72fc953.log`，SHA `7ed66395de13c91ee86b49579cbee188aaa999d0895c168cf80c88cf20640f3c`。裁剪后冻结九文件的新进程回归 **13 passed / 0 failed / 0 skipped**（306.02 秒），`s62closed-16eb91dd.log`，SHA `eaeb0228cb525ca526fe7b032befe747dd7acde0c00bd3e43f5e9e4408927912`。
- 邻接日志 `s62adj-479336c0.log` 为 **130 passed / 1 failed**（159.46 秒），SHA `3be399be5f4993b582d2853fdac023ad77af931e0b77ff08a1bb68723697dfa4`。该进程已加载裁剪前 consumer，唯一失败是新正文 parser 抢先拦截既有 coverage 低分变异；仅复用未变 API/SSE/纯 scope 层通过结果，consumer 的通过依据为上述 fresh run。未删旧 coverage 测试；不将重叠结果相加、不声称一次全量全绿。
- D 独立复验原固定 v4 小 fixture（SHA `e198dbfc5ec127645605f220b637353f83c75d27ab9fa6bea01169e488c113c4`）的原始配套篡改、unit hash、public scope 和 shortfall 输入漂移均被阻断，缺 rebound record 包括伪装 failed 均缺测，原分母 `[1,2,2,4]` 保持；无输入写入。另独立正式接口 **3 passed**（2.30 秒），日志 OS temp `1999wiki-d-s62-api-d0570ccd82c64914b5092aabd0ae4d08/pytest.log`，SHA `c9f6d50b468c9a49fc647b40db6da0b3f0e74d86f78d8d71b538a5c679058c49`，覆盖最终验证失败不提交会话、SSE 顺序及 REST/SSE 会话语义。九文件提交前后 SHA 一致，冻结输入与用户 main 脏文件不变。
- 新增四个本地 producer，总数 15，其余 41 项待完成，不是 15 项真实业务质量已通过。最终小 fixture 的 95 gold 保持，整体 `no_go`；未运行真实题集、embedding/Milvus/SSH/媒体/激活。已明确暴露一个旧运行时缺陷：复合 LLM 异常被通用 `_failed_branch` 错归为检索失败并丢失已生成 scope；新适用性门会正确计失败，而不是掩盖它。下一步仅放行下方 6.3 修复此状态保留问题，无需用户新裁决。

### 2026-09-10 第 6.3 项：复合回答异常保留已完成检索状态

- 基于 E 干净 `737b6aa`。根因与修复边界：全局来源分配/正常化完成后的私有 `_answer_composite_branch` 异常，当前被通用 `execute_request_plan` catch 丢回无阶段信息的 `_failed_branch`。在掌握该次实际 `branch_payload.route_decision` 与 `scope_normalization.result` 的现有私有 answer 调用边界处理普通回答异常，保留真实 effective route、retrieval outcome、scope；不得从 evaluator 观测反向驱动运行时，也不新建异常框架或重跑检索。`StoryRuntimeContractError` 的原 fail-closed 传播继续保留。
- 沿用原确定性失败答案/错误标识、`status=failed`、不可提交失败分支及未生成引用的处理，不改授权、模型调用/重试数或尽力回答策略。真正检索失败和进入正常化前的无记录失败继续保持 failed/null，不能伪造成功检索或 scope。局部成功分支仍可回答；请求级 outcome 继续只走已有聚合器，不另造汇总字段。生成失败不是检索失败，恢复元数据也不等于恢复答案成功。
- 消费层只移除已不再需要的“public failed 可与正常化 outcome 不同”兼容例外，改为关联该次实际结果；不改 oracle、分母、阈值、观测 schema 或缺测政策。保留旧事实的测试应升级为有效 RED：应当维持的真实检索状态/scope 尚未维持，而不是删除 applicability=0 的证据来造通过。
- 仅允许 `src/rag/execution.py`、`src/rag_eval/story_run_observations.py`、`tests/test_story_segment_runtime.py`、`tests/test_story_segment_eval.py`。原观测 test 的并发调用按 subtask ID 匹配对象身份，不依赖线程完成顺序；无需增加线程框架或压力测试。无新文件、回执、计划副本或公开 contracts 改动。
- E 有效 RED→最小修复→GREEN，覆盖复合生成失败、局部成功与失败并存、实际检索失败、早期 failure/契约异常、scope/唯一 outcome 四面投影、调用数和失败分支会话不提交；复用已有真实安装的小 fixture、API/SSE 邻接和冷评分，不进行完整题集/外部模型/向量/媒体操作。保持 Conda `1999wiki` 与 OS temp；不 stage/commit。完成后 D 独立验收提交，不继续自行扩展至其余 41 门或真实构建。

### 2026-09-10 前序检查点：第 6.1 项已验收

- D 将获批阈值修订以干净输入提交 `3999f541a63831b26f7acaf3778f5da64d8c08c6` 导入原 E 分支后，已独立验收并提交实现 `7372d8c3bd351b4bc413ff3522a21b108d892ef2`。仅下方约定四文件 `+111/-22`，生产代码净 +14 行，无新增模块、测试函数、运行时防御分支或监督回执；E 工作树/index 干净，尚未合并 main。
- 历史阈值 SHA 只取已验证 baseline receipt；当前复用既有 bundle，历史/当前用同一 loader 各解析一次，只比较两个历史 Recall gate 及其引用的分母定义。CLI 和实际消费入口都明确要求历史题集及历史阈值路径，不加可选空值兼容。新配置仍为原 wire schema；冻结输入、历史结果和 Spec 未改动。
- 有效 RED 为 **2 failed / 1 passed**（4.95 秒），日志 OS temp `s61red-0e58012b.log`，SHA `055836acde6fa42585e686a18d1b8730403941ca427528529af237b68a43d556`。最终一次受影响回归 **13 passed / 0 failed / 0 skipped**（210.32 秒），日志 `s61green-81503a48.log`，SHA `462cb8a2c743cb319de9f59d3fac6bb768ec6398b5f9dec4558e9098e0e1c582`；四文件 AST/compile、diff 检查通过。不重跑未变 runtime 全套，不把历史重叠测试累加。
- D 复用上一批已固定的小 fixture（observations SHA `ec15b69308133a061d2eec96aa39b2b926fe134646a00502a7e928d18a67c4a2`），以真实冷 `evaluate` CLI 独立运行当前 v1/历史 v1、当前 v2/历史 v1 两组；56 项除批准的分母元数据外与原报告一致，absolute quality、query diagnostics、95 gold 和 `no_go` 不变。当前/历史 SHA 错配各拒绝一次，拒绝不产生报告，采集入口和 socket 禁用，输入及四源文件前后零漂移。日志 OS temp `1999wiki-d-s61-4d9381f4470247e692b0bee016f74485/audit.log`，SHA `3a882e0a47fae4f25955e45c7442415b1c04f3f7543d4db4d5cb7d0af256f461`。这是本地消费者复验，不是真实题集采集或真实效果通过。
- 6.1 不新增指标 producer。原 S3 的 11 项已有本地 producer、45 项待完成及五条状态历史控制缺测均保持。D/E 已完成下一批实际接点的只读核定，现仅放行下方 6.2；无需用户重新批准分母修订。不重开 C/D0、会话或新评测框架，不自动执行真实构建或激活。每 30 分钟自检保持 ACTIVE，继续沿用用户已批准的人工裁决/低额度停止条件。

### 2026-09-10 第 6.2 项：同包 scope 与真实传输投影观测

- 基于原 E 干净提交 `7372d8c3bd351b4bc413ff3522a21b108d892ef2`，只补 `story_answer_scope_applicability_rate`、`story_answer_scope_normalization_rate`、`story_answer_scope_deterministic_bytes_rate`、`request_retrieval_outcome_projection_rate` 四门的本地 producer。输入沿用已冻结 v2 题集/v2 阈值，历史 v1 输入不动；不顺带扩展 Planner、召回、生成策略、性能控制或其他待测指标。
- `execution.py` 的单路 prepare 与复合路径共用原正常化入口，私有 frozen 记录只保留首次调用的实际实参和真实结果：subtask、已验证 context、内部 outcome、completed/frozen、最终 `retrieved.context_units` tuple 与 shortfall tuple。复用 `_BranchRetrievalEvidence` 携带，不把 `selection.context_units` 当作分配后最终 packet。记录必须在 LLM/引用处理前进入分支证据，不能仅在 `_answer_composite_branch` 成功返回后才保存；可把正常化移到其单一调用者并显式传入结果，不加可选回调、全局 observer 或线程局部捕获。公共 BranchResult/ResponsePacket 不新增输入镜像，正常业务仍只调用一次 normalizer。
- collector 对保留的同一输入对象调用原 pure normalizer 第二次，分别记录两次真实 canonical 结果。第二次仅属于评测观测，不重跑任何 Planner、授权、检索、LLM 或会话提交；计时仍按原边界，不能将额外投影耗时当 HTTP/TTFT 实测。两次 null、零次调用与结果缺失必须可区分；不得只序列化同一结果两次。cold evaluate 禁止调用 normalizer 或业务执行，只读观测。
- 正常 target 的完整有序子任务清单来自已验证 final plan；续页仅取 actual action 的 target subtask，复用 `_execution_planning`，不包含该 action 中未执行的兄弟任务。适用性对每个目标 present/null 决策计一次，包含合法非 Story/local/拒绝/boundary/needs-continuation/检索失败；不按非空 scope 或成功结果筛分母。沿用每题首个 candidate timed target 作质量样本，setup/warmup/其余计时重复不重复计数；协议拒绝无业务 packet，不伪造 scope 决策。未执行/不完整目标集仍未测。未经过 normalizer 的早期失败只能用实际终止结果证明 null，不伪造输入/调用；LLM或引用失败不得一概当检索失败。
- 独立 oracle 依据 Spec 的适用矩阵和实际冻结输入计算字段：零最终 unit 为 empty，有 unit 且 material shortfall 为 partial，否则 sufficient；claim 的默认与 narrative 映射、授权 coverage、身份、严格姿态按既定规则核对。不得调用待测 normalizer、其私有决策 helper，或从实测 scope 倒推期望。允许评测参考中少量、经明确正反例审查的独立常量/映射，不再建第二套产品规则引擎；不能复制运行时私有词表引用来自动自证。现有 gold 语义标签按其明确归属使用，不把 query 级标签强塞给所有复合分支，也不把 normalizer 正确率改成 Planner hint 或召回正确率。无法独立证明的项如实缺测，不猜默认通过。
- 正常化每个适用 packet 的两次实际结果都对 oracle 计分，分母为 `2 × 适用 packet 数`；确定性同样沿用此分母，同包两结果一致贡献 2，否则贡献 0。两次同样错误可通过字节一致门，但必须使正常化正确率失败。适用性错误不能通过缩小适用集掩盖；缺任一必要观测不能作全覆盖通过，零分母保持未通过。
- REST 在 `backend/schemas.py` 提取现有 packet→public→AskResponse 校验的小函数，由 `backend/main.py::ask` 与 collector 共用，collector 读取模型实际 JSON 投影；不 import main 来装配测试 app。SSE 在 `backend/sse.py` 提取 staged sources（PreparedExecution）与 done（ResponsePacket）的既有 payload 构造，由真实 generator 在原阶段及 collector 共用，后者经过实际 `sse_event` 编码/解码取值。内部直接读最终 packet 的唯一 RouteDecision；不读 diagnostics、不调用 legacy `response_packet_to_sse_events` 冒充 staged 路、不复制四份 public dict、不另起 ask/stream 请求或 replay chain。
- 此处是同一次业务执行的正式传输投影复验，不声称两次 HTTP 请求端到端实测或测得 sources 的真实到达时刻。现有 API/SSE 测试必须证明正式入口调用这些共享函数、sources 在生成 token 前、done 来自 finalize 后 packet，单独破坏任何投影能被识别，缺失 done 不能补造。实际生成/校验异常提前终止仍按原行为，不为评测伪造成功 done；HTTP/TTFT 门保持 pending。
- 落盘仅新增正常化需要的完成/冻结标志、内部 outcome、最终 unit 有序身份/摘要、实际 shortfall 和两次 canonical 结果；plan/context 用已有 ID/identity 关联，不复制整份计划、registry 或正文。传输仅新增实际取到的四个 outcome 观测，不生成第二个业务汇总状态。`observations` 严格字段/schema 同步修订一次，不自动升级历史观测、不产生新 sidecar/receipt/ledger/runner；性能报告只有现有消费必须随 schema 适配的部分，不新增测量。
- 允许修改五个现有生产文件：`src/rag/execution.py`、`backend/main.py`、`backend/schemas.py`、`backend/sse.py`、`src/rag_eval/story_run_observations.py`；四个现有测试文件：`tests/test_story_answer_scope.py`、`tests/test_story_segment_runtime.py`、`tests/test_sse.py`、`tests/test_story_segment_eval.py`。复用 serializer/normalizer 原算法，不改公开 contracts、chain、runner、build 或冻结输入，不新增文件。若实际必要改动超出本范围，先向 D 说明具体接点，由 D 判断，不自行延伸。
- E 在既有测试中完成有效 RED→最小实现→GREEN：正常/复合/续页/empty/null 矩阵、分配后的最终 unit 实参、真实两次调用与调用数不增加、两次同错/不同/缺失、完整子任务集、独立破坏投影及 diagnostics 冲突、真实正式入口顺序、cold 禁执行、双阈值身份/95 gold/no_go 保持。跑四门受影响测试与真实 API/SSE 邻接；复用未改动全套结果，不反复重跑整条构建链。Conda `1999wiki`、小 fixture、OS temp；无真实题集、embedding/Milvus/SSH/媒体/激活。E 不 stage/commit、不新增计划/回执，完成后留 D 独立审查提交；即使本地四门 producer 完成，也不得声称真实效果、E 最终交付或整体 go。

### 2026-09-10 前序检查点：第 5 项已验收，适用性分母修订已批准

- D 已在原 E 分支提交 `c6cc6fd54f0603229561d089c06b1145280368ab`（parent `f10a63c`），九文件 `+1072/-175`，工作树/index 干净，尚未合并 main。新增量主要在现有评测消费者与测试；`src/rag` 两文件净 +10 行，仅保留实际续页 context 和精确 decoder 异常/trace 接点。没有新模块、runner、框架或监督回执。
- 严格 v1/v2 loader、真实 setup/commit/continuation/anchor、observations/v3 与 performance/v2 已贯通。续页 planning 如实为 null，沿原 action 与本次已验证的具体 context 消费，只执行目标 subtask；不重新授权或伪造 envelope。D 审查发现的缺测误计零分已关闭：未执行 target 的受影响指标保持缺测，不送入 gate；保留全部 95 组 gold，真实 completed 空检索/拒绝仍计零命中。仅 80 条逐字段/来源一致的 direct 例关联旧控制，五条状态例的历史控制仍不可用，相关比较保持 pending。
- E 原完整 baseline/eval/runtime 是 **185 passed / 3 failed**，三个失败为新增参数/字段的旧测试调用未迁移，日志 OS temp `cvfull-2c6a1527.log`，SHA `49e773eea5d1477eea93d2fb0ad45d6027cc4272a379247bb7222611ced04065`。迁移及 P1/context 修正后最终受影响 **10 passed**，日志 `cvgfinal-7cca5c6e.log`，SHA `bf58be5762ad52878e4da3341e52a540e7c0eeed9be99eb28d1cf79d5474698e`；五文件 API/会话/授权/执行/复合邻接 **255 passed**，日志 `cvadjfinal-216a0cad.log`，SHA `7e4417db998318641b852de01d76d3ae984cb2652ab78c8bed3bcfebf45a62e1`。按 D 授权复用未改动 baseline/runtime 的已通过覆盖，不声称一次全量全绿，也不把重叠结果相加成独立测试数。
- D 独立 SSE 全文件及两个 loader/实际续页节点 **54 passed**，日志 OS temp `1999wiki-d-consumer-28e4e5c05c864ee7880b4561a1c34ab9/pytest.log`，SHA `d663a56cb2e127f05629f61e80bb8b009e35ad6d8be64668075a496c6aca66f3`；另对最终小 fixture 产物作 8 项只读复验，覆盖完整观测、context/来源漂移、提交身份、终止 trace、候选不可伪装 unsupported 及 95 组缺测口径，未重新采集。九文件审查/提交前后 SHA 一致；冻结五输入与 Spec 无变化。原 RED 与 P1 RED 普通日志保留，无新证据层。
- 本批完成不等于 E 最终交付或真实效果通过。11 项已有本地 producer、其余 45 项待完成及整体 `no_go` 不变，未执行真实题集、embedding/Milvus/SSH/媒体/激活。后续只读核定及用户裁决已完成，当时仅放行下面的第 6.1 项，现已验收如上；不重开 C/D0、旧 Step 6 或新 E 会话，不因本批提交自动进入真实构建。main 用户原有脏文件未触碰。

### 2026-09-10 第 6.1 项：适用性分母与历史阈值身份解耦

- 用户批准将 scope 适用性与归一化/一致性的分母分开，并要求克制代码膨胀。适用性覆盖目标子任务的 present/null 决策，包含应有和不应有 scope 的分支，每个目标决策计一次；归一化与一致性仍覆盖所有适用冻结 Story evidence packet、每包实际归一化两次。阈值仍为 1.00；setup 不是 target，未执行/缺失 target 仍未测，协议拒绝不制造业务 packet。此为验收计数修订，不改变产品适用矩阵、检索/生成行为或召回门槛。
- D 冻结新配置 `eval/story_segment_thresholds.v2.json`，SHA `b995e8eb7de46f33281e3bfb5c12a90d351ac6c09b01a0fb23c95e2a94fa0759`。仅增加 `all_target_scope_applicability_decisions` 定义并将 `story_answer_scope_applicability_rate.denominator` 指向它；其他 55 项、全部数值/方向/基线关系、旧分母定义保持。文件 v2 是策略数据修订，字段结构未变，仍使用 `rag.story-segment-thresholds/v1` wire schema 和已有 loader；不新增 schema 分支。旧 v1 配置、五份历史输入和 Spec 原字节保留。Git 仅精确 unignore 这一个新配置文件；后续输入一律来自已提交字节。
- 当前 `_baseline_final_hits` 将历史 baseline 的阈值整文件 SHA 等同于本轮阈值 SHA，导致本次不影响 Recall 的分母修订也会错误阻断旧 Recall 对照。修正这个身份职责：历史 receipt 继续固定其原阈值文件；本轮 candidate/evaluator 独立固定当前阈值文件。`evaluate` 新增一个必填 `--baseline-thresholds` 路径，预期 SHA 只能取已验证 baseline receipt 的 `inputs.thresholds_sha256`，不另加用户自报哈希。当前阈值复用既有已验证 bundle 的阈值对象；历史阈值用同一个 loader 读一次。当前消费历史结果的 `final_evidence_recall` 与 `middle_late_final_evidence_recall_delta` 两门，逐项要求 gate 定义及其引用的分母定义与历史相同；不同就拒绝借用，不提供自动迁移/重采集。仅非比较的 scope 适用性分母修订不破坏这两个对照。报告分别保留当前及历史阈值身份，不覆写旧 receipt，不放宽 baseline business/case/equivalence/gold/80 direct 关联检查；五条状态控制仍缺测。
- 代码仅允许 E 的 `src/rag_eval/story_run_observations.py`、`scripts/evaluate_story_segment_rag.py`、`tests/test_story_segment_eval.py`、`tests/test_story_segment_baseline.py`。D 先把已提交的新配置和对应 `.gitignore` 单行导入同一 E 分支作为干净输入检查点；E 不读取其他工作树未提交数据、不自行编辑冻结配置。无需修改现有 threshold loader、runtime、capture、runner、模型/API、授权或正常化函数；不为此引入通用策略继承、版本迁移、观测/回执框架或重复执行路径。
- 在现有测试节点先证明新阈值与历史 Recall 对照被错误整文件 SHA 拒绝，再实现最小职责拆分。GREEN 覆盖 v1 同版本与 v2 当前/v1 历史、全部 56 门及数值不变、仅已批准分母变化、历史文件错 SHA/Recall gate 或其分母变化拒绝、80 direct/95 gold 与缺测规则保持、CLI 参数与输出输入路径保护、冷消费者不触发执行/网络。修复缺陷的测试针对真实边界，不为不相关极端输入增加防御分支；已有类型/身份校验不重复执行，已验证进程内对象直接复用。
- 完成后跑受影响 eval/threshold/baseline 节点及必要 CLI 邻接，给出准确日志和最终范围供 D 独立复验。只用 Conda `1999wiki`、小 fixture 和 OS temp，不重复未变化的整套 runtime 回归。E 不 stage/commit、不新增文档或 receipt；D 形成独立检查点。本项不新增任何质量门的通过声明，也不伪造同包两次归一化、内部 RouteDecision 或 REST/SSE 观测。缺失的 scope packet 观测与四面投影留在原 S3，D 依据现有接点另定一个连贯实现范围，不让 E自行扩大本项。

### 2026-09-09 前序检查点：anchor 已验收，v2 输入已冻结

- D 已在原 E 分支提交 `4b1682fa0c9f00127304ec219ee6912d2234d218`：六文件 `+379/-4`，生产四文件净 +64 行，无新模块、公开 schema、宽松兼容或监督回执。原 anchor helper 经正常 execute/prepare 入口消费真实已提交 turn；授权、envelope 重验、action builder 共用同一 projection/UTC。缺失、过期、身份漂移、双 Story clear、实体冲突、多 required、无回指及 local/open-domain 边界保持；未授权时保留原 direct-query 拒绝。E 树/index 干净，尚未合并 main。
- E 完整 runtime/authorization/conversation/request-plan **299 passed**，日志 OS temp `anfull-159a3ac5.log`，SHA `411169759bf2f4f45b780a767883438a70d83d3e8873ffbddf5cc5ea8bdeb184`。新增测试曾暴露四处不合法 Planner fixture 和旧 fixture 的 candidate/legacy Retriever 混配；只修正测试输入及同源安装，生产未为测试放宽。最终签名测试精确接受原五项加 keyword-only projection/UTC。
- D 独立 **116 + 59 passed**：四文件 API/执行/复合/SSE 邻接日志 `1999wiki-d-anchor-adj-b69b0357c9194f43ac9cf0dbdd99e1d9/pytest.log`，SHA `5921138aafa6d0606c2bc755568ac072a1325f848c38a638df62f016b2812724`；16 项新入口和完整 route-policy 日志 `1999wiki-d-anchor-entry-ef5f78bd59de4c509fcd6b011f8132f4/pytest.log`，SHA `3adc57d770d151e76f63663fd48e9ad3f0e0951e2f363680c3dbe3b1b39a5791`。六文件前后 SHA 一致；同五文件邻接由 D 的实际结果覆盖，不要求 E 再重复一遍。有效入口 RED 和最小 GREEN 已保存在历史暂停提交 `dee63b0`，不因恢复重跑。
- D/main 提交 `ffffdc688dc4a251441ecff53ceafa2c307f0214` 冻结 v2 输入（SHA `20499bcbac896b6ff5ba14c65db657a7fe0669b6d5db5136365f0845371a6160`）；85 例只修订获批五例，80 普通用例与全部 95 组 gold 不变。下文明确真实前序/目标分离、拒绝口径及历史不可比范围。输入冻结不等于 collector 已能消费，不伪造新 baseline。
- D 把同字节 v2 输入导入 E 固定提交 `f10a63cbc6cca8dceaa769b03ece2c0886ff6f11`，不依赖 D 工作树的未提交文件；基于该提交执行的单一消费者批现已完成，结果与接续边界见上方当前检查点。旧暂停现场及哈希由 Git 历史追溯，用户其它脏文件未触碰。

## 2026-09-05：保留功能、收敛实现与验收流程

用户已选择 **1A + 2A**：保留已批准的功能、用户可见行为、质量门槛和安全约束，允许合并重复流程与证据格式，并把验证放在实际证据产生之后。本节是 D/E 后续收敛工作的共同执行依据；与下文、E Plan 或旧 D2 契约冲突的**流程要求**以本节为准。原 Spec 的产品能力和安全不变量不因本修订被删除。

### 保留的结果与现有状态

- 保留 A 的授权路由、复合问答和双开关语义，B 的中文 Analyzer，以及 C 的自然名称、主题、剧情与来源支持的媒体绑定能力。
- 保留 E 的结构/分支信息、Atom BM25、Segment Dense、Typed Dense、融合与预算、多剧情比较、continuation、anchor、AnswerScope、Atom citation 和 REST/SSE 一致性。
- 保留来源与产物身份校验、Owner/授权边界、准确的失败/空检索区分、引用闭包和会话提交原子性。
- 真实 embedding/Milvus 仍由 D 在 E 合并后执行；仍检查云端容量，构建后保留至少 12 GiB，Story Segment 不超过 25,000；不得自动激活、覆盖 active collection 或下载媒体。
- C 与 D0 已完成的提交和证据继续有效。E 在现有工作树、现有会话上继续；按用户最新设置，后续执行使用 `gpt-6-astra / xhigh / 普通速度`，不由历史 Plan 的模型或快速模式条款覆盖。恢复前分别核对模型、思考等级和 service tier；不能仅关闭快速模式选项就假定已切换普通速度。
- 2026-09-05 的历史收敛起点为 E HEAD `c81d336806cd9f0b3abb32db01054287df14d711` 及当时 11 个未提交文件；它已被后续验收提交替代，不是当前恢复门。当前起点只取文档顶部的最新执行项。已有改动、失败构建和验收证据保留；不得为了拆提交而重置或重放整条历史。

### 需要关闭的根因

1. Story 文本候选构建无条件进入完整媒体组装，导致文本派生能力被独立的媒体缺失阻断。
2. 打包要求预先提交离线评测，而部分指标需要该次构建的输出；现有 56 项指标中 17 项缺观测，不能将其当作真实效果不达标或自动通过。
3. 配置、字段和校验多处定义；一次性交接路径、固定机器目录与固定历史 blocker 数进入通用构建逻辑。
4. 全零操作计数缺少观测来源，部分测试只检查未接入实际调用路径的 Mock；这不能替代真实的外部调用边界验证。

### 串行收敛批次

| 批次 | 交付内容 | 验收 |
|---|---|---|
| S1 共享规则 | 先合并 Story 融合配置的重复定义；构建与运行时共用一个不依赖客户端或文件系统的配置模型。保留既有导入接口，不建立通用配置框架。 | 配置 JSON 与 SHA-256、排序/预算结果、非法输入拒绝行为保持不变；相关现有测试前后通过。 |
| S2 候选职责 | D 明确文本候选的产物集合和消费者，E 在既有构建链内区分文本派生与媒体重建阶段；构建、评测、打包各有明确输入输出，D/E 入口共享实现。 | 无媒体本地字节时仍可严格验证文本候选；文本来源/引用错误仍阻断；媒体未完成状态完整保留，不能把它发布为媒体通过。 |
| S3 真实观测 | 将 56 项指标逐项映射到已有 producer 或补齐缺失 producer，按证据产生阶段执行；移除无观测依据的“实测零次”声明。 | 指标名称、阈值和业务语义保持；未测明确标为待验证，不能默认通过；最终 go/no-go 不允许缺项。 |
| S4 实现收敛 | 围绕 S2/S3 实际触及的代码合并重复解析与验证，拆分职责过多的函数；移除被替代且未发布的重复构建路径。 | 同一业务用例得到同等结果；新旧产物必要兼容保留；不新增泛化框架或只为减少单文件行数的转发层。 |
| S5 完整交付 | E 定向与完整回归、真实离线重建和 handoff；D 独立验收、合并及合并后回归，再执行真实 shadow 和最终评测。 | 保留原功能、真实质量与安全退出条件；通过不等于激活。 |

S2 开始编码前，D 必须依据现有消费者写清文本产物集合、媒体引用方式和阶段状态；不能用忽略所有媒体 blocker、伪造空媒体产物或放宽完整候选验证来实现。只读沿用既有媒体证据不代表新绑定已被验证。S1 可独立执行，不依赖 S2 的新产物。

### S2 首批：先拆保真核对职责，不切换公开契约

- S1 已由 D 独立复核：27 项定向测试通过、85 组新旧配置对照一致，fusion identity 保持不变；不把配置去重称为整个收敛任务完成。
- S2 首批只允许修改 E 的 `src/huiji_rag/build/fidelity.py` 与 `tests/test_huiji_corpus_fidelity.py`。从现有 `build_fidelity_ledger` 抽出文本逐记录核对：Parent/Child、exclusion、Story migration 和 child BM25 共用原算法；媒体关系与 media BM25 继续由完整入口执行。此批不修改投影、writer、候选 schema、CLI 或任何运行时授权逻辑。
- 保持 `build_fidelity_ledger` 的签名、`FidelityResult` 的公开字段，以及完整结果的 ledger、build_diff、分类、blocker、排序和拒绝行为不变。内部文本结果不得伪装成全量成功；不得通过构造空 `LegacyMediaReconciliation`、过滤 blocker 或新增宽松模式完成拆分。允许一个必要的私有结果结构，不建立通用验证框架。
- D 的改前基线为现有 fidelity 文件 30 项测试通过。E 先保留现有测试的行为基线，再进行等价抽取；补充小规模完整输出对照及文本阶段不调用媒体核对的断言。改后运行同文件和既有 artifact writer 的邻接回归，使用 Conda `1999wiki` 与 OS temp basetemp，不创建逐修复 receipt，不执行真实快照。D 独立复核前不提交、不进入下一批。
- 后续文本候选至少需要 10 项核心产物（现有 tuple 去除 `media_assets`、`media_bm25`），但 **10 项清单本身并不构成完整闭包**：registry、budget、其他实际消费的配置/结构 sidecar、来源与文本 fidelity 必须一并纳入可验证引用。D 在接口批开始前统一定稿，而非让各消费者自行猜测路径或 schema。
- 后续接口批须同时解决 candidate 路径基准：当前 D3 将引用重基到 project root，而 storage、typed shadow 和 runtime 按 candidate 文档父目录解析；runtime 又按固定文件名读取 registry/budget。必须使用一致的文档/引用解析规则，实际穿过 storage loader、fake typed builder 与 runtime install 验证，不能仅以 parser 通过声称端到端可消费。原 active v1 的媒体解析与安全边界不变。

S2 首批只准备可复用的文本核对逻辑，不宣称已解除真实文本构建的媒体阻断。文本构建、媒体状态和完整候选发布状态的接口切换另在同一 E 工作树串行完成。

### S2 第二批：共享 Story/Typed 文本写入步骤

- 首批已由 D 验收并在 E 提交 `721f56ff005478027129b9148987814765c6380f`。本批只修改 E 的 `src/huiji_rag/build/artifact_writer.py` 与 `tests/test_huiji_corpus_artifacts.py`；保留其已有 provenance 修正，不重置其他未提交工作。
- 在现有 writer 模块中抽出 Story sidecar 与 Typed Dense 文件的实际写入步骤，合并重复的 JSON/JSONL 写入样板；输入只包含文本、Story bundle、身份和已有文件目录信息，不接收完整媒体 request。复用已有低层写入器和 schema 定义，不增加泛化框架、另一套构建入口或纯转发模块。
- 完整入口必须调用该共享步骤；保留当前 12 项 candidate 契约、所有产物字节/文件集合、manifest 元数据、create-new 语义、媒体/voice/fidelity gate、公开签名与验证器。此批不改 schema、路径基准、CLI、状态模型或运行时消费者，不提前把文本阶段称为发布通过。
- 以改前现有 42 项 writer 测试和小型完整产物字节为基线；改后验证 Story 共享步骤不触及媒体且生成相同文本文件，完整入口继续拒绝来源/媒体错误，并运行真实调用 writer 的既有小型 builder 测试。只使用本地 fixture，不执行真实快照或外部调用；D 复核前不提交、不进入接口批。
- 本批结束后进入 S2 产物/路径/消费者的统一接口批，不再为继续拆私有 helper 增加准备批次。涉及已有未提交文件的提交应按实际依赖收拢，不为了制造独立提交重写历史或丢失旧修改。
- 本批已由 D 验收：E 的 45 项回归、D 的 3 项独立测试通过；D 对照正常/阻断/仅诊断/媒体不可用四种状态，共 129 个输出文件字节一致，60 个既有定义及公开签名未变。生产代码净减 57 行，新增测试 60 行；代码仍保留在 E 的既有未提交集合内，待接口依赖一起验收提交，未合并 main。验收时 writer SHA-256 为 `5df1752ac172d2b5e706d61200fbb4886fe02b4bee5c62777e91f062ece6a044`，测试 SHA-256 为 `3c2437c0bd05bb3d0ca05c54d7e5af5607d0f9065a7406653a8cb1912eeb7144`。

### S2 接口批：文本产物闭包与统一消费者

本批替换 E 尚未发布的 Story→完整媒体构建路径，不把旧路径保留为另一种 Story 构建模式。C 已有全量 Corpus/Media V3 入口、active v1 解析及媒体 gate 仍保留；复用其来源恢复、投影、文本 fidelity、BM25 和 Story/Typed 算法，不复制整个构建器。以下规则是 D 冻结的内部接口决定，不改变产品功能或质量阈值。

**产物与单一事实源：** 在同一 immutable 文本根目录生成下列 21 项文件。文件名、schema 和逻辑角色在现有 contracts 中用一个领域专用的固定目录表定义，writer/parser 消费同一表，不建立通用 registry 框架。

| 组 | 文件/逻辑角色 |
|---|---|
| 基础文本 4 项 | `parent_blocks.jsonl`、`child_blocks.jsonl`、`excluded_entities.jsonl`、`indexes/child_text_bm25.json`；逻辑名沿用 `parent_blocks`、`child_blocks`、`excluded_entities`、`child_bm25`。 |
| Story 12 项 | 第二批已有的 taxonomy、entity_link_registry、atom_structure 与 schema、segment_config、segments 与 schema、atom_to_segment 与 schema、context_budget、context_units schema、context_fixture。逻辑名为 `story_structure_taxonomy`、`story_entity_link_registry`、`story_atom_structure`、`story_atom_structure_schema`、`story_segment_config`、`story_segments`、`story_segment_schema`、`story_atom_to_segment`、`story_atom_to_segment_schema`、`story_context_budget`、`story_context_unit_schema`、`story_context_fixture`；沿用现有文件名/schema。 |
| Typed Dense 3 项 | 沿用 `dense_retrieval_units.v1.jsonl`、`.schema.json`、`.manifest.json` 及现有三个逻辑名/schema。 |
| 文本 fidelity 2 项 | `diagnostic/text_fidelity_ledger.v1.jsonl`（沿用逐记录 ledger row schema）、`diagnostic/text_build_diff.v1.json`（`huiji.text-build-diff/v1`，仅文本 active/candidate/category counts、真实 blocker 和 unexplained_parent_child_loss；不得声明媒体通过或把媒体缺失写成零）。 |

- `text_artifact_manifest.v1.json` 使用 `huiji.story-text-artifacts-manifest/v1`，是上述文件路径、schema、hash、大小、行数的唯一发布清单；同时绑定 source inventory、代码/配置身份、原 fidelity baseline、已有 `story_structure` 来源证据和文本阶段状态。原始 C 证据继续 hash-pinned，不复制或改写旧 receipt。媒体标记 `deferred`，详情引用现有 C release 中的延期证据，不重算或核销旧 blocker。
- `story_candidate_build_input.v2.json` / `rag.story-candidate-build-input/v2` 的 wire fields 精确为：`schema_version`、`story_retrieval_capability`、`text_artifact_manifest`、`config_identities`、`expected_milvus_schema`、`embedding_identity`、`provenance_identities`、`ordered_tuple_sha256`。manifest ref 包含 `relative_path/sha256/size_bytes`；其余身份含义沿用现有规则。**不再序列化第二套 `artifacts` 与 `typed_dense` 内容**：现有对象属性从已验证 manifest/typed manifest 一次解析得到只读视图，供现有消费者使用。全部 21 项都要校验，运行时实际消费其中 18 项；来源/保真不能因不参与检索而脱离清单。
- manifest 不引用自身或 candidate，避免循环哈希；candidate 单向绑定 manifest。构造对象时允许 candidate 尚未写出，但最终文本 bundle verifier 必须验证恰好 21 项数据文件 + manifest + candidate、candidate→manifest 绑定，以及来源/结构/映射/文本 fidelity 的实际闭包。复用现有严格 Story source-truth 验证，不靠布尔声明通过。运行时读取 D 已验证的文件身份，不要求云端挂载本机原始 C 数据路径。
- 旧 E candidate v1 属未发布中间产物：明确拒绝并要求重新构建，不做 silent migration、宽松 fallback 或双格式 Story 生产。active v1 不受此决定影响。

**阶段边界与状态：**

- 在既有 `HuijiCorpusBuilder` 中贯通独立的 Story 文本阶段；可替换现有 E 专用 `build_story_candidate` 的返回契约。全量 `build_candidate`/完整媒体 writer/verifier 继续使用原完整 gate。新的文本结果不得伪装成完整 `CorpusBuildResult` 或完整 `FidelityResult`。
- 文本阶段只读取四份已恢复来源及文本 baseline（Parent/Child/exclusion/child BM25），保留恢复校验、source join blocker、投影闭包、C Story 来源验证和 pre/post source identity；不调用媒体本地字节检查、VoiceBinding、MinIO/Wiki 媒体兼容、媒体容量规划或 legacy media reconciliation。它们仍属于保留的完整媒体入口，不是被忽略的文本 blocker。
- 第一批文本核对结果提升为明确的文本结果/入口，继续复用原逐记录算法，并保留排序、重复身份拒绝和 loss 检查；完整 fidelity 仍组合真实媒体核对。文本终态仅 `text_verified` 或 `blocked`，媒体状态始终 `deferred`。`text_verified` 仅证明文本产物，不能意味着评测通过、真实向量就绪、媒体完成或可以激活。
- 构建先产出文本，再运行依赖该产物的评测，最后打包。S2 的本地 bundle 可在评测尚未执行时存在，但必须标为待评测，不能因缺报告而伪造通过，也不能调用 fake Dense 来补真实指标。S3 才补真实 observation producer；旧 56 项阈值/gold 不变，最终 handoff 与 D go/no-go 仍要求各自阶段的完整有效证据。

**路径与接线：** candidate 的 manifest ref 相对 candidate 所在目录；manifest 内文件 ref 相对 manifest 所在目录。固定同根布局，禁止 repository-root rebase、`..`/绝对路径逃逸或猜测备用目录。registry/budget 也通过已验证逻辑引用读取，不再另猜固定文件名。E/D 使用同一业务构建与打包实现；打包如需复制，复制完整文本 bundle 并保持 candidate/manifest 字节和相对布局不变，不重新声明一套 hash。D3 receipt 引用该 bundle；不得只复制 candidate 文件。storage probe、fake typed builder、runtime snapshot v2/install 必须实际读到这个 bundle。完整媒体文件不进入该文本包，现有 active 媒体只由原 active snapshot 消费；D 的真实容量预检仍计算最终文本包/暂存/索引增长并保留 12 GiB 与 25,000 Segment 上限。

**实施范围与退出：** 仅在 E 原工作树串行完成本接口批。生产允许 `build/{__init__,contracts,fidelity,artifact_writer,orchestrator}.py`、`src/huiji_rag/runtime_artifacts.py`、`src/rag/chain.py`（仅安装/文件消费）、`scripts/{build_story_segment_candidate,build_huiji_typed_index,probe_story_segment_storage}.py`；测试允许现有 corpus artifacts/builder/fidelity/builder_contracts、dense_retrieval_units、typed_shadow_builder、story_segment_runtime/eval/structure 文件。若确需统一重复 fixture，可新增一个 `tests/story_candidate_fixture.py` 并移除原重复构造；不得新增产品模块、监督器或通用测试框架。不修改 Planner/授权/融合算法、媒体实现、投影语义、真实 evaluator producer 或 frozen eval 文件。

先用有意义的失败测试暴露无媒体字节的文本构建、缺 registry/budget、打包后实际 loader 失败；再贯通 producer→打包→storage→fake typed build→runtime install。还须验证文本损失/来源篡改/映射篡改仍阻断、同输入两根目录语义一致、完整非 Story Corpus/Media/active v1 回归、外部调用边界和非法旧 candidate 拒绝。只运行本地 fixture；本批不运行真实全量快照、embedding、Milvus 或媒体操作，不更新旧 D2 字节、不生成新监督 receipt、不提交。D 独立验收后与已有重叠改动按实际依赖成组提交；最终真实构建留在 S5。

**S2 真实消费者联调发现的 Owner 接线修正：** 已发布的 C Atom/Segment/Typed Dense 使用来源 `story_entity_id`（例如 `1`），E0 registry 与授权 context 使用带类型的稳定键（例如 `story:1`）；不能按字面直接比较，也不能为对齐测试改写 C 数据。D 允许本批额外修改 `src/rag/story_authorization.py`、`src/rag/retriever.py` 和 `tests/test_story_authorization.py`，仅完成这一既有身份边界的精确接线，不改变授权算法或公开契约。

- 在现有 detector 的已验证 Parent 索引上提供一个精确的 registry-key → 原始 Story ID 查询；只查带类型的注册键，拒绝未知键/非 Story 键，不用前缀剥离、raw-ID fallback、模糊匹配、默认放开或新增序列化映射。保持输入 Owner 顺序与一对一关系；不重新检测问题或改变授权集合。
- `retrieve_story_branch_v2` 先完成原有授权/branch filter 闭包，再在同一入口映射一次。候选检索与预算/context 选择共用这个存储 ID 元组；原 context、required refs、公开 branch filter、continuation 和 anchor 继续使用原授权键。不得修改 Atom/Segment/Typed 行、Dense 过滤算法、融合/预算算法、引用身份或注册表产物。
- 当前本地打包→storage→fake typed→安装后的业务失败是本修正的 RED。验收必须穿过真实 Policy/授权 context 与 `retrieve_story_branch_v2`，验证命中、来源/预算闭包及未授权 Story 隔离；覆盖 direct、continuation、anchor 共用映射、open-domain 不变及未知/跨类型键在检索前拒绝。旧 fixture 改为遵守真实 producer 的 ID 契约，不用给假候选补前缀掩盖问题。继续使用既有测试与普通日志，不新建修复回执；本修正及 S2 相邻回归通过后由 D 一并复核。

**S1/S2 本地检查点（D 已验收）：** E 提交 `59604cb79b33b3cf9b3fa9762fca6b27e5c21ad5` 保存当前相互依赖的 22 个文件，包含此前未提交的构建脚本和评测测试，不代表本接口批新增了全部 diff。提交后工作树与 index 干净；尚未合并 main。S2 生产者、23 文件包、实际 storage/fake typed/runtime 消费、Owner 精确映射及同实体重复 Parent 的一致性去重已贯通；冲突事实仍拒绝。D 的 corpus 回归 105 项、eval/typed/dense 回归 102 项通过；后者运行中有共享 fixture 更新，因此最终固定版本另验 23 项（29 项被 `-k story` 排除），9 个相关文件前后 SHA 无变化。E 最终 runtime 全文件 47 项、authorization 139 项通过；没有把测试替身当作真实向量质量证据。

- 最终 D 日志：`C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s2-final-20c19abd5ca4\pytest.log`，SHA-256 `9f48aec7bc57f5eb66be12ef624d389b96a6acb8bdfe92244f92939ca8f8ba8b`；E runtime 日志：`C:\Users\HUAWEI\AppData\Local\Temp\s2-local-859515f324b34a5aadc849917b10d6eb.log`，SHA-256 `910c7a8c26c5231c63cd7598eea6931ca3c0a12f6d74a3ccab94fe9912b994f1`。这些是普通测试记录，不生成额外监督回执；此前上下文压缩失败未改变已核验的测试结果。
- 此检查点仅关闭 S1/S2 本地范围。真实快照、真实观测 producer、最终 handoff 正向路径、S4 收敛及 S5 完整交付仍待完成。现有 runner 的临时观测接线一并保存以保持依赖，但不得因此称其通过 S3。没有下载媒体、调用 embedding/Milvus 或更改生产激活状态。

### 验收顺序与证据含义

1. **代码回归：** 验证授权、引用、预算、continuation、anchor 和接口行为；fake Dense 只验证算法及接线。
2. **离线产物：** 先生成文本/结构/Segment/typed 输入，再对这些确切产物验证来源、映射、词法召回、预算及可离线测量的指标。
3. **E 交接：** 只在全部离线要求通过后交接；明确列出只能由真实 embedding/Milvus 得到的待测指标。此状态仅允许 D 进入后续安全预检，不是最终质量通过。
4. **D 真实构建：** 容量、目标 collection 与写入边界先通过，才执行 embedding/Milvus；最终 runtime snapshot 只在真实构建和写后校验完成后生成。
5. **最终评测：** 使用真实候选及对应对照产生结果，覆盖全部 56 项要求；任何缺观测、未测或未通过项均不能得到最终 go。

哪些指标属于各阶段，由 D 对照其计算所需输入逐项确定，不按当前实现方便程度分组。既有阈值和 gold 不降低；fake 指标不用于证明真实 Dense 质量。这里替代旧 D2 中“全部 56 项必须在真实向量构建前通过”的时序要求，不减少最终验收内容。

S3 的已确认修复边界：当前 `story_segment_runner` 依赖 runtime snapshot 上并未实现的 `execute_measured_story_query`、`observed_dense_ranks` 和 `observed_capacity_evidence`，且真实 CLI 仍转入 fake Dense 评分核心。应使用明确的运行执行器产生观测，snapshot 继续只表示已验证的产物身份；性能与质量消费同源运行观测，fake 与真实结果明确区分。不得给不可变 snapshot 临时塞入测试属性，或以传入自报计数代替真实调用记录。6 项产物、24 项本地流程、26 项真实运行的初步分组需在 S3 按全部冻结分母和 producer 逐项验实后固化，不是当前已通过清单；最终仍要求全部 56 项完整有效。

S3 同时迁移既有 `emit_story_segment_handoff`/validator 的旧 flat candidate v1 与内联 `typed_dense` 假设，使其消费本节唯一 v2 文本包，并与 D 统一继任交接契约。当前因 `evaluation_pending`/`operation_observations_pending` 正确拒绝打包，只证明未完成状态不会被误放行，**不证明最终 handoff 正向路径可用**。真实观测闭合后须恢复正向交接验收；不能添加 v1 兼容退路或临时伪造 ready。

**S3 首个实现批次：补齐已冻结的基线约束。** `_passes_gate` 当前忽略 `baseline_relation="not_below"`，使达到绝对下限但退于真实基线的值可能通过。仅允许修改 E 的 `src/rag_eval/story_segment_runner.py` 中评分判定和 `tests/test_story_segment_eval.py` 对应测试：先用冻结的 BM25/最终证据 recall gate 验证“达下限但低于基线”失败，再在既有判定上同时执行原绝对阈值与基线关系。覆盖低于/等于/高于基线、仍低于绝对下限、缺观测与零分母；复用已有所有 gate 回归，不改阈值、指标字段、producer、snapshot、调用链或 handoff，不新增文件或回执。D 验收后独立提交。此批只修判定遗漏；基线来源、排名/分母和真实观测仍属于后续 S3，不能以本批单测通过宣称实测质量通过。

本小批已由 D 验收并在 E 提交 `71dbf6cdc8f20bd9ac14c089bad0232ab80612e0`：生产 +2 行、测试 +48 行，只有上述两文件。E 的 RED 为预期的 2 failed/10 passed，GREEN 与邻接回归 24 passed；D 固定文件版本独立 16 passed，测试前后两文件 SHA 不变。D 日志 `C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-baseline-26eeda6eba3845b0890343b40d10a6ce\pytest.log`，SHA-256 `243441dc3d1396eba669327a8d3bba29350332278f700e02776c57df4868fb65`；E GREEN 日志 `C:\Users\HUAWEI\AppData\Local\Temp\s3-baseline-green-b723b65e627e4a91abeb8b8d1471db2e.log`，SHA-256 `515c3ebb1f4e0c06857f8f9fe656f216e771f01e7bb930634c15def0084072fb`。四份冻结评测输入未变，E 提交后工作树/index 干净；仍未合并 main，也未完成其余 S3/S5。

**S3 只读对应核查（非质量通过）：** 56 项 producer/分母/阶段清单已在既有 E 任务 `01a0646c-69ee-74f3-a513-5724a0d3c8ef` 的执行轮 `01a06fb8-0b24-7f71-8ab0-affc20e5c8b7` 汇总，不另建一套监督回执。17 项尚无观测计算；其他项有公式也不代表已有真实 producer。必须修正独立 active baseline、Dense 与 fused 排名分离、Atom group/适用事件全集分母、REST/SSE sources/done 独立投影、canonical continuation 全页及调用边界观测；不得把 `len(cases)`、`max(1, …)`、自报零次或 candidate 自身冒充这些输入。优先复用现有 trace、授权 envelope、检索/context/response 对象，不把观测塞进 snapshot。每查询全 Segment 遍历须据实测量并处理；关系 precision/recall 的独立审定集合尚需从已批准证据定位，不由 registry 自证正确。E 提议将阶段初分调整为 6 产物/26 本地/24 真实，仍待逐批定稿，不能据此放行最终 handoff。

### 简化后的监督与变更规则

**S3 下一批：两个离线产物指标的实际 producer。** 仅放行 E 的 `src/rag_eval/story_segment_runner.py`、`scripts/evaluate_story_segment_rag.py`、`tests/test_story_segment_eval.py`。在现有评测 CLI 增加 `artifacts` 子命令，输入为 `--candidate-build-input/--expected-candidate-build-input-sha256`、`--thresholds/--expected-thresholds-sha256` 与独立 `--output`；一次通过既有 v2 parser 和 23 文件布局校验，不初始化配置客户端、runtime snapshot、网络或 fake Dense。复用 `evaluate_hard_gates` 的 56 条九字段指标行，在普通报告顶层标记 `evaluation_stage="artifacts"` 并绑定 candidate 原始 SHA/ordered tuple、manifest SHA 与 thresholds SHA；没有对应观测的其余 54 项继续 `passed=false`，报告总状态 `no_go`，不增加 ready/激活语义或新的监督回执。输出在输入文本包之外，不改写原 bundle。

- `typed_dense_story_segment_row_limit`：分母为已校验 typed JSONL 的实际总行数，candidate/numerator 为其中 `retrieval_unit_type=story_segment` 的实际行数；不读取自报 capacity 字典，不硬编码历史计数。
- `oversized_atom_mapping_body_citation_closure_rate`：按已校验规范 Story Atom 正文的 Unicode code point 长度与该包 `hard_max_chars` 动态选出完整分母，不仅依赖 `quality_flags` 或只验证首个 context fixture。对每个超长 Atom 复用现有 Segment/Atom→Segment/ContextUnit、正文渲染与 citation/source 映射规则，证明单 Atom 映射、完整 span/正文/hash/source refs/citation 闭合；不截断、不重分块、不复制一套 renderer。零分母遵循现有不通过规则，不能补成 1 或伪造已测通过。
- RED/GREEN 必须穿过真实小型来源→23 文件 writer→评测入口：覆盖普通/超长混合、超长不在首个 Segment、所有超长 Atom 均计入、正常阈值边界判定、候选/阈值哈希及行数/映射/正文篡改拒绝，以及原产物字节零漂移和不触发外部客户端。允许复用已有 fixture/变异 helper；不改 build/ContextUnit/运行时产品文件，不建立新领域框架或 56 个 adapter。若现有接口确实不足，先报告精确接口缺口；不在本批顺手扩大授权。定向与评分/CLI/ContextUnit 邻接回归后由 D 独立验收提交；不运行真实全量快照或旧 Build A。

**本批已验收：** E 提交 `0404ccb303fb88ef6d94cf6b1f3347758f7f3961`，严格为上述三文件：生产 +114 行、测试 +243 行，无新模块/回执。E 真实 bundle→CLI RED 2 项失败，canonical Atom 与下游 source refs 同时错配的补充 RED 1 项失败；最终定向 18 项和邻接 36 项通过。D 固定版本独立 43 项通过，三份代码、四份冻结评测输入及 Spec 共 8 个对象前后 SHA 零漂移；D 日志 `C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-artifacts-502a1151124448a18a4af4ce049149fe\pytest.log`，SHA-256 `02f7bc4a46e656fe32f391fa3d73016380681a57b9f0b8338a85e538f8d81c34`。E 定向/邻接日志 SHA 分别为 `dcc5d49f10a229fe609a5f7b3876a95139552d78e263fcbe7f6bf529c3e3b5e6` / `e30b11306a815bb4e216e9b2e3a171f586e81859fa86d185f75d5f1c274940ab`，普通日志路径保留在既有 E 执行轮 `01a07003-a2a8-7443-95ee-69e75eda9030`。提交后 E 工作树/index 干净，尚未合并 main；只证明两个产物 producer 的本地调用闭包，其他 54 项在该报告中仍未观测、总状态 `no_go`。真实 executor、独立 baseline、排名/分母修正和最终 v2 handoff 正向路径仍待完成；未执行真实快照、外部构建或激活。

**S3 下一批：一次业务执行的内部结果出口。** 仅允许 E 修改 `src/rag/execution.py`、`src/rag_eval/story_segment_runner.py`、`tests/test_story_segment_runtime.py`、`tests/test_story_segment_eval.py`。在既有 `RAGExecutionService` 内将当前单次执行主体提取为一个共同私有入口，返回该次 `PreparedExecution` 与 `ResponsePacket`；原 `execute` 继续调用同一主体并仅返回原回答包，公开签名和产品行为不变。评测侧显式接收已安装的真实 chain、请求/会话与期望的候选 snapshot 身份，复用该共同入口以及 `RequestTrace`，保留同一次执行的准备结果、最终回答包与 trace snapshot；至多增加一个必要的内部不可变结果结构，不添加通用 callback/observer 框架、另一条生成流程、snapshot 动态属性或新的序列化回执。

- 评测入口在执行前核对真实 `StoryRuntimeBundle` 的已验证安装身份及期望 snapshot；不绕过既有 resolver、vector adapter、collection/schema/embedding 校验。不在本批构造另一套工厂；本地测试使用真实小来源→23 文件→resolver/install→正常 `RAGChain` 构造，外部 planner/LLM/vector 边界使用受控替身。
- 普通 grounded、local/immediate 与复合 Story 分支均只执行一次。复合请求可能已经在 prepare 内完成分支生成并返回 immediate packet，必须原样沿用；禁止评测侧再次生成/检索。结果消费复用现有 serializer 与 trace 投影进行只读验证，不新增只为展示“双消费者”的空适配器。最终上下文/source map/citation 必须来自实际准备/回答包，不能由 gold 或预制 `case_evidence` 填充。
- trace 保留已有字段的原始含义：同步 `invoke` 返回后的 `model_first_token_ms` 不能被新入口解释为实测 TTFT；复合 prepare 的总耗时不能被解释为纯 retrieval。此批不出具 latency/quality gate、raw Dense/BM25/fused 排名或调用次数的缺测零值，不宣称已关闭 performance/evaluate 的跨进程复用。CLI、performance receipt、56 项评分、运行时产物 schema、raw-rank producer 和最终 handoff 不在本批修改；它们后续必须消费同源实际观测，不能以本批内部出口通过代替端到端验收。
- 先以实际执行测试暴露结果出口缺失，再做共同主体抽取；验证两种调用入口的回答/citation/context 行为相同，普通和复合生成计数无额外增加，本地分支不生成，身份错配在执行前失败。对同一个结果多次调用现有 serializer/trace 投影时，以禁用执行入口的反例确认不会重跑。运行现有 execute、Story runtime、断供/补充分支和 eval 邻接测试，Conda `1999wiki`、OS temp、普通日志；D 独立复核前不提交、不进入后续批次。不得恢复旧 Step 6/Build A、创建新 E、运行真实全量快照或外部服务。

**单次执行出口已由 D 验收：** E 提交 `d7b924928e532fbb1a3a5744b0a1e88c830bff6b`，仅上述四文件，生产 +63/-4（净 +59）行、测试 +196 行，没有新文件/工厂/回调/CLI/回执。有效 RED 为首组 7 项与补跑 multi 2 项；夹具的版本字段、授权身份和 `mixed` 预期错误未计作产品 RED。E 定向 9 项、普通执行/tracing 52 项、Story/eval 邻接 25 项通过；D 改前 52 项及改后独立 79 项均通过，后者包含上批全部产物指标回归，四份代码、四份冻结评测输入和 Spec 前后 SHA 零漂移。D 日志 `C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-execution-final-30e6a738dc8d4af5b4bcf537d0a2beab\pytest.log`，SHA-256 `396a13c25059abee353b81931a56724afe91ab300a32525f39c3b73787354580`；E 日志/hash/argv 保留在既有执行轮 `01a07033-a74d-7220-a61e-6e96e8a1b1ca`，D 已核对原文件。原 `execute` 签名未变，其余原有函数/测试 AST 未改写；提交后 E 工作树/index 干净，未合并 main。正常构造链已验证普通、即时、单 Story 和真实 local+Story 双子任务的生成计数与回答/引用等价。

本批仅提供内部 `(prepared, response, trace)` 实际结果。现有 composite aggregate `context` 为空的行为保持，不能从空字段或最终摘要伪造逐分支模型输入；逐分支上下文、raw Dense/BM25/fused 排名、可靠时序/调用观测及跨 CLI 同源持久化仍需后续接线。旧 CLI 的 snapshot 方法缺口、独立评分和最终 v2 handoff 仍未关闭，不把本批局部通过称为完整 S3。未运行真实快照、外部服务或激活。

**S3 当前放行批：真实通道排名与分支检索结果贯通。** 起点为 E `d7b924928e532fbb1a3a5744b0a1e88c830bff6b`。仅允许生产四文件 `src/rag/{story_retrieval,retriever,chain,execution}.py` 与测试四文件 `tests/{test_story_retrieval_fusion,test_retriever,test_story_segment_runtime,test_story_segment_eval}.py`；runner 已返回 `PreparedExecution`，不另加出口。复用既有候选结果、context selection 和单次执行链，不新增产品模块、公开 schema、observer/callback、跨请求 last-query 状态、CLI 或 receipt。

- 在既有 `StoryCandidateRetrievalResult` 保留轻量不可变原始排名行：Atom ID/实际 BM25 rank/score、Segment ID/Owner/实际 Dense rank/score，以及本次 normalized query 与 Owner/关系过滤条件。范围是既有通道上限内的实际返回（Atom 80、Segment 30，使用同一 config），不额外检索、扩大窗口或保留整份重复正文。Dense 原始顺序已经受 query-by-vector 的 Owner 条件限制，不称为全库排名；BM25 既有零分行原样保留。Owner 过滤后、关系过滤后仅保存指向原始行的有序 rank 引用，不复制多套分数；保留原始名次缺口。融合顺序直接复用现有 `segment_candidates`，seed/expanded/最终 context 顺序不能冒充融合顺序。未提供的 score 不补零；不为观测改变原有验证、排序、过滤、预算或错误语义。
- Retriever 返回同次内部候选对象，chain 在原返回组装处透传；不放入 public route/diagnostics/trace。`PreparedExecution` 携带按最终 subtask 顺序排列的内部分支检索证据，允许一个必要的小型不可变分支结构。单分支来自原 retrieved，composite 在原 `payloads`/`answer_branch` 处保留同次候选、selection 及全局引用重绑后的真实 context/source_map，私有 `_execute_composite` 唯一调用点随包返回证据。以 subtask ID 关联既有分支结果，不再次执行检索或生成，不重新分配引用，不重复序列化 selection。这里的 context 是检索上下文，不是完整模型消息或最终摘要；aggregate 空 context 的既有公开行为不变。
- 成功检索的空排名与 local/拒绝/依赖失败的未获得完整观测必须区分；缺候选对象使用 `None` 并结合既有 branch status/outcome，不默认空 tuple 或实测零次。Dense 中途失败时本批不追捞半程 BM25；明确完整候选观测不可用，不能声称 BM25 没运行。Child Dense、真实 TTFT、56 项评分/独立 baseline 与跨 CLI 持久化均未因本批自动闭合。
- 新增有效 RED 验证原始、Owner/关系过滤、融合、seed 和最终选择有不同顺序时仍能准确保留；包括原始名次缺口/实际分数、同 Segment 多 Atom、80/30 截断、成功空与缺测区分。用真实小型 BM25 和已安装正常链穿过已有评测出口；覆盖单 Story、local+Story、两个 Story 子任务的证据关联与确定性排序、实际引用重绑 context/source_map，以及禁用执行/客户端后重复读取不重跑。原公开回答、引用、生成次数与 REST/SSE 字段保持，未授权原始候选只可内部观察，不进入用户上下文或对外响应；Dense 越 Owner 仍硬拒绝。
- D 改前 fusion/普通与复合执行/Retriever 共 82 passed、14 failed；14 项根因为旧 Retriever fixture 缺 S2 已要求的 `detector.story_source_ids`，不是本批新 RED。仅迁移夹具为真实 registry + canonical Parent 验证的 detector，并同步区分 typed registry key 与 raw Story ID；禁止 identity lambda、raw fallback 或修改生产 Owner 门禁。改前日志 `C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-ranks-before-d5a3cb03523a488a8775f9f65030b11f\pytest.log`，SHA-256 `87331660f37245119b14606a9cb790c9ff10af2218a68f98df1cd1b778659bbe`。改后运行上述文件及现有 Story 断供/补充/授权/预算与公开序列化邻接回归，由 D 独立验收后提交。本批不执行真实快照/旧 Step 6/Build A、embedding/Milvus、SSH、媒体或激活，不改冻结评测输入与旧 D2。

**通道排名与分支证据批已由 D 验收：** E 提交 `a4d1a54ec31ce9f2656c65fdf9265d93b3342b5e`，仅上述八文件，总 +338/-7，生产净 +74、测试净 +257 行，无新文件/框架/回执。候选保留轻量原始排名与筛选引用，融合继续复用原对象；分支证据不复制 outcome，按 subtask ID 使用最终 `BranchResult` 唯一状态。E 有效 RED 10 failed；旧 fixture 迁移后 29 passed，最终定向 10 passed、核心 99 passed、邻接 304 passed。夹具缺 aliases、双 Story 固定 S01 触发既有 repair、typed/raw Owner 混用这三类测试修正已闭合，未计作新增产品 RED，未放宽门禁或调用数断言。E 日志/argv/SHA 保留在既有执行轮 `01a0706d-e2f2-7e10-bc84-376b365268ed`，D 已核对原日志，其中邻接日志 SHA 为 `e3d8036446982c3a7f845f70c04f50830ddb86c2d5ce0cebf692ed462b7ce576`。

D 固定版本独立 **264 passed / 3 个既有弃用警告 / 547.88 秒**，覆盖完整 Story runtime、核心四文件、SSE/tracing/预算、本次实际执行评测出口和此前产物 gate；日志 `C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-ranks-final-ca3e4d2e45e2499cb9964a7d7e8facfa\pytest.log`，SHA-256 `d3fa4fb48d126b7d7313951f74eb7e5b7e62901a56d00a50e1726390aa757006`。八份代码/测试、四份冻结输入和 Spec 共 13 个对象在独立验收前后 SHA 零漂移。去除观测增量后，候选检索、Retriever、chain.retrieve、prepare 与 composite 五处原主体 AST 一致；其余原函数未被改写。真实未授权 Atom ID 的分支/全局 REST/SSE 隔离、双 Story 两次生成且零 repair、观测重复读取不重跑均已通过。提交后 E 工作树/index 干净、任务 idle，仍未合并 main；原始 Dense 只表示带 Owner filter 的实际查询返回，依赖失败仍是完整候选观测不可用。真实 TTFT、Child Dense 观测、独立基线/56 项评分、跨 CLI 同源持久化和最终 v2 handoff 仍待后续 S3/S5，不以本批本地结果宣称真实质量或发布通过。未执行真实快照、外部服务、媒体或激活。

**S3 当前放行：真实装配、一次采集与跨 CLI 只读消费。** 起点 E `a4d1a54ec31ce9f2656c65fdf9265d93b3342b5e`。用户已明确普通批次交接无需再等其批准：D 验收当前批后可自行安排既定 S3/S4/S5 后续工作，仍不跨越外部写入和最终质量门。此批生产允许 `src/rag_eval/story_segment_runner.py`、`scripts/evaluate_story_segment_rag.py`、`src/rag/retriever.py`，测试允许 `tests/test_story_segment_eval.py`、`tests/test_story_segment_runtime.py`、`tests/test_retriever.py`；若需避免 runner 继续膨胀，允许唯一新增 `src/rag_eval/story_run_observations.py`，必须承担完整的观测投影/文件验证/只读消费职责，并移走相应旧实现，不得是纯转发层或泛化框架。

- **装配：** 原 active 配置只读。active lane 使用真实固定 v1 snapshot、原 collection、原 Retriever/RAGChain；candidate 只用独立连接配置选择已验证 shadow collection，`StoryRuntimeBundle.install` 继续用原 active 配置校验。candidate Retriever 显式消费 exact verified v2 对象与其 candidate manifest 文本引用，不给 v2 加 v1 假属性、不伪造混合 tuple、不改全局 `cfg.huiji`/collection、不走 minimal-test/legacy fallback。candidate lexicon 显式取 candidate Parent，媒体显式使用固定 active snapshot；现有 RAGChain 注入参数足够，不另造工厂框架。真正 resolver/file proof 保留；不得用测试替身伪造 Retriever 或安装对象。
- **candidate-only Child 边界：** 从已验证 typed Dense 的 `child` 行一次得到 canonical Child-ID 集合，普通 structured/expand 共用该 Child 池。普通 BM25 仍读取原 hash-pinned 全量 Child BM25，按原 query/limit 查询，再在进入融合前按同一集合过滤；保留 rank/score/Analyzer/原语料统计，不重建缩小索引、不补满窗口。candidate 普通 Dense 调用原 `embed_query` 一次及 typed query-by-vector `retrieval_unit_types=("child",)`，后续原 Owner gate 保留；返回类型/ID 必须属于 canonical Child 集合，类型违例硬拒绝，不重试 generic search、不补零分。Story Atom 仍保留在原 Child BM25 产物并由授权 Story 分支的 Atom index 消费，Segment 只走 Story Dense。active v1 的算法/兼容行为不变，不改 Analyzer、融合、预算或授权规则。
- **一次采集：** CLI 新增唯一 `collect`：`--queries/--expected-queries-sha256`、`--active-runtime-snapshot/--expected-active-runtime-snapshot-sha256`、`--candidate-runtime-snapshot/--expected-candidate-runtime-snapshot-sha256`、`--warmup-count`（至少 1）、`--timed-samples-per-query`（至少 5）、`--reranker-disabled`、`--output`。先核对所有输入，再装配各 lane 一次；固定 active 全部样本→candidate 全部样本，每个 query 的 warmup 与 timed 均恰好一次 `_execute_once`。每个样本用独立空会话和真实冻结 query；此批不伪造 continuation/action/anchor 状态，因此这类专项门仍待独立合法场景 producer，不冒称其已测。warmup 全保留但不入正式统计；所有 timed 样本保留，逐 query 质量投影固定首个 timed sample，绝不挑最好结果或合并多次排名。一次输入查询和已有 RequestPlan 的多分支执行保持原业务语义。
- **单一数据文件：** `rag.story-run-observations/v1`，create-new canonical JSON，绑定 run ID/采集提交、公开非秘密配置身份、机器/计时器、query raw SHA/有序 ID、warmup/timed 计划，以及明确区分的 active v1 source raw SHA/tuple/collection 与 candidate v2 snapshot raw SHA/ordered tuple/candidate/manifest/shadow receipt/embedding 身份。样本唯一键为 `(lane, query_id, phase, sample_index)`，保存同次实际请求、轻量 raw/filter/fused/seed/selected ID 顺序、实际重绑 context/source_map、现有公开 response 与原 trace。只保留实际 context/answer 正文，不 `asdict` 整个 selection/Document 复制正文；outcome 仅在最终响应分支。缺观测为 null，成功空为 []，不从 gold 预填或给 snapshot 加动态属性。采集失败不能生成完整成功文件；不自动拼接不同 run 的半成品。输出不得覆盖输入、位于不可变 bundle 内或覆盖已有文件。
- 样本同时保留已取得的真实 `RequestAuthorizationEnvelope`（若有，使用现成 `request_authorization_envelope_to_dict`；非 v2 明确 null），以及公开 serializer 未暴露的实际 `ResponsePacket.citation_validation/turn_outcome`、按 subtask ID 关联的 `BranchResult.status/citation_validation`。outcome 仍只存最终分支的一份；不重复检测/规划，不复制 prompt、LLM 草稿或已验证全 registry，不从 gold 填充事务事实。此项只避免落盘时丢掉同次已取得的依据，不意味着新增授权/会话指标已通过。
- **真正只读消费者：** `performance-control` 改为只接 `--observations/--expected-observations-sha256/--output`；`evaluate` 改为 `--observations/--expected-observations-sha256`、`--queries/--expected-queries-sha256`、`--thresholds/--expected-thresholds-sha256`、`--candidate-build-input/--expected-candidate-build-input-sha256`、`--output-root`。两个命令独立加载同一文件、严格核对 canonical bytes/字段、两 lane 身份、query/sample 全集、顺序/重复/缺失与所给输入哈希；不构造客户端/chain、不再查询 active 当前状态、不执行问题、不从另一份衍生 receipt 回追输入。后者 candidate 使用既有离线 v2 parser/layout verifier，不调用 runtime resolver。每个产出直接绑定 observation raw SHA，不建立 receipt 链。新默认路径移除 `_runtime_query_runner/_measured_runtime_observation` 的虚构 snapshot 方法，以及 CLI 的重复执行/fake Dense/自报 capacity 评分路径；旧未发布测试 seam 不得成为真实 CLI 兼容退路。
- **本批报告的真实含义：** 性能输出 `rag.story-run-performance/v1`，从全部 timed 样本原 trace/明确测量区间计算有据的 P50/P95 与实际样本覆盖，列出 pending stages，完整性未满足时 `no_go`。sync 执行耗时单独标为 internal execution，不能充作真实 HTTP 总耗时；sync invoke completion 不能充作 TTFT，composite prepare 不能充作纯 retrieval。原严格性能 v1 不能接收 null 或第二种无判别形状；历史 helper 可供明确 fixture/历史验证，不产生假的完整 receipt。质量输出沿用 56 行九字段 gate report，增加 evaluation stage/输入身份与从首个 timed 实际样本算出的逐 query 检索诊断（各通道/融合/最终来源的 ID 顺序、实际基数和缺测状态），并复用两个已验收 artifact producer；尚未具备独立 subset/分母/baseline 的质量 gate 继续不通过，不能从诊断数量推造 Recall。本批关闭采集与消费路径，不宣称 56 指标完成。REST/SSE 同包序列化不冒充独立端点实测。
- **验证和范围退出：** 使用真实小来源→23 文件→D4 fixture 和包含真实 active/provenance 配置形状的 factory，外部 Milvus/embedding/planner/LLM 只在测试边界替身；generic candidate string search 禁用。覆盖 active/candidate 文件/collection/lexicon/media 隔离、原配置与 active 哈希零漂移、合法 typed Child、Segment/Story Atom/错误 Child 拒绝且不 fallback、原授权 Story 仍可取回证据。collect→文件→两个 CLI 的正向路径必须运行；两个消费者在禁用执行器/所有外部客户端后反序重复调用仍成功，验证各样本只执行一次、完整 sample keys、缺 timing 不补零、非重复事实源、所有 hash/schema/缺失重复/lane 交换/覆盖输出拒绝。新增 meaningful RED 后最小实现，运行此前核心/完整 Story runtime/授权/公开/tracing/产物与相关 CLI 回归；D 独立验收后提交，再继续下一必要闭包。冻结 gold/threshold/Spec、原 D2/snapshot 字节不动；不运行真实全量快照、旧 Build A、真实 embedding/LLM/Milvus/SSH/媒体或激活。

**一次采集与只读消费批已由 D 验收：** E 检查点 `0b6bf2cf44a66b0a3fbe0003b1c56a64d97e81f5`，仅上述七文件（含唯一新观测模块），总 +1093/-711，生产净 +350、测试净 +32 行；移除虚构 snapshot executor 和 CLI 重复执行路径，没有新增 supervisor、receipt 链或兼容分支。最终核心 100、完整 eval/CLI 102、runtime/授权/公开/tracing/typed/artifact 邻接 490，共 692 passed、零失败/跳过。完整 argv、日志与七文件身份保留在既有 E 执行轮 `01a070d2-954e-7700-9cf7-1f1c3704f7ce`；D 已核验 eval 日志 `C:\Users\HUAWEI\AppData\Local\Temp\oceval-5a4c9e2a.log`（SHA `3895ce5ea1c49774cbe5c86dafb8c9114a43e2a67c3da3806015aa3eb33190e3`）与邻接日志 `C:\Users\HUAWEI\AppData\Local\Temp\ocadj-d1b56f7c.log`（SHA `d664ecc1fba1bb7fb80ac730c4fc9d85060db78f3413014d1d7977b65d23285c`）。

D 独立定向 **37 passed**（`C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-collect-review-82a2153f1fdd402fb16ded2c73c5aff5\pytest.log`，SHA `196a2dd3fbab265df454ebf5357100d512472a1f29c205561e7d4ff934593ce0`），业务/授权/公开等合同 **422 passed**（`C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-collect-contracts-f91b5bcd92294a90817d799e8a5311fa\pytest.log`，SHA `3a9c825795210328ec465a74e8ab21092e8591497f15e6eabc01e740f8ea4bca`）；七文件验收至提交前 SHA 零漂移，四冻结 eval、Spec、D2 原字节不变。candidate 条件增量移除后，Retriever 原 active load/BM25/Dense 主体 AST 一致，其余十个方法未改。D 另在两个新 Python 进程中禁用网络、live config/resolver、chain 构造与执行，分别运行两个消费者成功：`C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-s3-cold-consumers-1700ca08d11e4a23a3acb2cd95943fe5` 的 `performance.log` SHA `078374f1912896ba2c0790252a88c82780867e77347ac0fdb43c1e004b36898c`、`evaluate.log` SHA `64e95fe601901cc9428177df8420716d4fce53dc1f96123f2add22bc8bf4a3c5`。1,032 个 fixture 样本只证明实际采样顺序/次数与文件消费，不代表冻结 85 题的真实模型质量；正向 Story probe 使用真实 registry 身份的合法显式 Planner proposal。缺失的阶段/质量证据仍 pending/no_go。E 提交后树/index 干净，尚未合并 main，未执行真实快照、外部服务、媒体或激活。

本批的两个边界澄清：公开 `SubtaskInfo` 已含最终 status/outcome，观测直接保存它，不复制第二份状态；internal 只补未公开的 validation/turn outcome。collect 保护已知 active/text/D4 输入根，evaluate 保护已知 candidate bundle/输入，performance 只保护其已知输入与 create-new；不为未知历史根增加路径字段或扫描。D 真实执行的输出必须放在独立评测目录。代码提交从模块所属仓库 `git -C` 获取，代码/公开配置身份在装配前固定，不取任意调用 cwd 的提交。

**紧接下一项：Planner 真实提案生产闭包，先只读定案。** D 已核对真实失败观测 `C:\Users\HUAWEI\AppData\Local\Temp\ocg3-958d7d81\test_collect_cli_executes_each0\observations.json`（SHA `fa2fff32e8dbda721dcf6067dc10d403879a8dbd8dcc493fcf5099fb814ba3c7`）：同一 `Story01` 的 Planner ID 为 `01`、Detector ID 为 `story:01`，其余 registry/span/hash 相同，结果为 `denied/story_mention_set_mismatch/not_applicable`。`query_plan.py` 自动补引用直接使用 Parent raw ID；真实 LLM 输入又没有 registry/hash 构造依据，提示词却要求完整引用，故不能仅加前缀或改测试就宣称正常 Planner 可用。E 先在上述提交上只读核对“LLM 传输提案→本地规范化→冻结 QueryPlan 引用→独立授权”的最小闭环与必要文件/测试范围，向 D 给出短方案，不写新文档、不实施。D 定案后再放行一个根因批；无需用户为普通阶段交接再次批准。不得让 Policy/Detector 替 Planner 修正遗漏或授权交集，不改 raw Owner/注册表事实、三授权来源、单次扫描/Finalizer、缺证据门、冻结 Spec/gold；不引入新注册表事实源、全 registry 提示词、兼容猜测或 supervisor 层。正常 Planner 根因仍未完成，不以本批 checkpoint 声称 S3 完成。

**Planner 根因批已由 D 定案并放行实现：** 起点仍为 E `0b6bf2cf44a66b0a3fbe0003b1c56a64d97e81f5`。生产仅允许 `src/rag/query_plan.py`、`src/rag/chain.py`、`src/rag/story_authorization.py`；测试仅允许 `tests/test_query_plan.py`、`tests/test_story_segment_runtime.py`、`tests/test_story_segment_eval.py`，不新增模块、文档、schema 产物或兼容层。E 只读方案在既有轮 `01a070f5-2189-7f13-8911-55fd669cf21e`；D 确认 Spec `STORYBRANCH-P0-10/16` 固定的是内部提案和独立比较，本次只替换模型传输适配，内部引用/授权协议不变。

- 已安装 v2 明确选择唯一模型 wire：保留原语义字段，显式 `branch_kind`，并要求 `story_mentions=[{"query_char_start":0,"query_char_end":7}]`，无提案用 `[]`。每项只含子查询 Unicode code-point 范围；不让 LLM 输出 ID/hash/receipt 或授权字段，不接受旧完整 `planner_story_entity_refs` 作为 v2 模型兼容入口。能力来自已安装的静态事实，不按模型字段是否存在猜版本；active/v1 原有行为保留。原内部 `QueryPlan.planner_story_entity_refs` 仍按同一严格 schema 生成，现有 RequestPlanner 子查询→原问题 span 映射不改。
- 从 Detector 已验证的 Parent 元组和同版 registry 身份/normalization 只暴露引用原不可变值的静态视图；Planner 不接收 Detector 实例、扫描方法或检测结果，不重载/复制第二份 registry，不把全 registry 发给 LLM。该视图替代单独可指定的 registry hash 参数。只解析模型明确给出的切片，精确查规范名、alias、typed ID 和原静态 resolution 优先级；typed ID 取已验证值，不拼/剥前缀，raw Owner 不改。只为该项计算原文 SHA/机械元数据，不扫描补齐所有提及，不查更早位置，不排序/去重/修正遗漏。有效但错的个数/顺序/首次 span 仍交原独立 Policy 拒绝；非法 wire/越界/未知或歧义键明确 fail-closed，不救回成泛化检索，也不把早停算作已完成检测或成功事务。v2 移除旧的“缺 branch 才自动补 ref”路径。
- 四组 meaningful RED→最小实现：真实 `plan()` 无 SHA wire 的单/多 Story、alias/typed ID/Unicode 与 raw/typed 分离；空/遗漏/重复/倒序/后次 span 原样被独立 Policy 拒绝，以及非法/旧 wire 拒绝；现有不连续 source span 映射与一次 Detector/既有 Planner 调用数、混合 local/非 Story 保留；真实小来源/23 文件/D4 factory 的 collect 改用正常 span wire，原 `01`/`story:01` 拒绝样例转为授权取证且两个冷消费者仍工作。覆盖原 `story_required/story_mentions/story_examples` 语义分支；不得因构造 Story 引用而改写既有 primary Owner、角色/主题语义或普通无 Story 行为。测试中旧完整 hash-ref 模型替身可迁移，负面断言和授权策略不弱化。
- `story_authorization.py` 仅新增必要静态视图暴露，检测/授权算法及其身份保持；chain 仅注入该视图。RequestPlan/Finalizer/continuation/anchor、Retriever/预算/融合、观测模块、snapshot、Spec/gold/D2 均不改。D 改前独立四文件 **303 passed**：`C:\Users\HUAWEI\AppData\Local\Temp\1999wiki-d-planner-before-5765ada1839149d8aa020405cbff1ca2\pytest.log`，SHA `f33f2380834c2b3fb457f76ca162e0de0ea5df6dc55d852351c56d6a8fba508a`。改后运行完整 planner/request-plan/授权、runtime/eval、route/retriever/公开/SSE 邻接；D 验收后独立检查点，再继续 S3。沿用 Conda 与 OS temp、禁止真实外部服务/全量快照/媒体/激活，不新增监督证据层。若测试暴露此范围之外的新根，先向 D 批量报告，不悄悄扩文件或降低门槛。

本批独立审查补充：短角色/主题名与长 Story 标题并列时，旧全类型最长匹配会覆盖已明确的 primary Owner。只在 installed-v2 的显式 Story-bearing character/topic 提案中，使用同一静态事实、原问题中的名称/别名证据和原 Lexicon 验证主体；不由 branch 声明凭空指定 Owner，不改 active/v1 或普通问题。完整邻接另暴露 `tests/test_route_policy.py::test_dense_dependency_failure_is_not_reported_as_empty` 的旧 `Retriever.__new__` fixture 缺少构造器必设的 `_candidate_child_ids=None`；D 仅额外放行该测试文件补齐初始化，保留原异常分类和不泄漏断言。不得为这个 fixture 修改生产 Retriever 或增加缺字段兼容。本批最终允许七文件，其余边界不变。

**Planner 检查点已验收：** D 在 E 提交 `06a942af630d8657418e598e906255a6499ab02b`，七文件 `+375/-62`，其中生产净增 86 行，未新增模块/证据层。E 最终同版本十二文件回归 **628 passed / 0 failed / 0 skipped**，日志 `C:\Users\HUAWEI\AppData\Local\Temp\plfinal-98a91238.log`，SHA `a4569ab7ba8b51bcaba75552ebdad9583f8219e1516123a05b57a7e3b060677b`。D 独立覆盖 **353 个不同用例**：四核心、真实安装/collect 与 route 首轮为 352 passed + 1 已知旧 fixture 失败（`1999wiki-d-planner-final-e0026d2174324032a3d82406b96ac644\pytest.log`，SHA `f330a877bc88e8bd2dc8f7ad8e32d7453d053a95aafa1a8793f0b1c4ffd207dc`）；仅补齐该 fixture 后完整 route 43 passed（`1999wiki-d-route-fixture-final-b24d083041d74ca2a5c3aeece910560b\pytest.log`，SHA `b22b8f21e03f5e1829f8d21db109d9c6bc67995d0c3fd5aede6b9e9169ba8888`，两目录均在 OS temp）。前后其余六文件及最终七文件验收至提交 SHA 不变；原 Detector/授权、QueryPlan 协议与 fallback AST 不变，Spec/D2/四 eval 原字节不变。提交后 E 树/index 干净；尚未合并 main，未执行真实模型/快照/向量或媒体。正常 span wire 已穿过真实本地 factory 与独立 Policy，但 fixture 模型不代表冻结题集的真实效果。

**S3 紧接下一项，先只读定案：** E 在上述固定提交核对现有 `story_run_observations` 中的真实事务、scope assignment、授权和最终分支事实，给出下一组可直接由已采集证据计算的质量指标短方案；D 同步核对冻结 gold/baseline 的分母和适用条件。区分代码可验证的不变量、必须对照独立 gold 的正确率、尚缺执行观测的指标；不能以自身观测充当 gold，不能把 receipt 自校验当作完整业务正确率，也不能复用旧 fixture 平铺字段伪装真实 producer。先列最小连贯指标组、精确分子/分母、现有输入路径和确实缺少的证据；不修改代码/文档/gold，不启动新 E、真实快照或外部服务。D 定案后才在同一工作树放行实现，无需用户为正常批次转换再次批准。

**S3 最终必要证据覆盖批已定案：** 上述只读轮 `01a07130-30f0-72c3-9a0a-353fe9c4ab02` 已完成，D 同意在 E `06a942a` 上仅实现以下两项真实 producer。生产只允许 `src/rag_eval/story_run_observations.py`、`src/rag_eval/story_segment_runner.py`；测试只允许 `tests/test_story_segment_eval.py`。保留现有 collect/两个冷消费者、CLI 参数、观测 schema、56 项九字段报告和未测项不通过；不改运行时、Spec/gold/阈值或 D2，不新增模块/receipt/采集入口。artifact loader/索引在一次 evaluate 中共用，旧 artifact 入口签名与两项原指标保持，不重复加载/验证同一个 bundle，也不建立全局缓存。

- `story_explicit_one_to_three_owner_coverage`：分母从冻结 gold 的 direct-query、明确要求 1～3 Owner 的字段确定（当前 70 例：60/7/3 个单/双/三 Owner 用例，不硬编码数量）。分子必须同时证明原顺序/完整授权集合正确、同一 KB 任务承载多 Owner 比较，以及每个 required Owner 至少有一个完整有效 Segment 留在该分支最终 grounded context。使用真实最终 Plan/context、selection、source_map、分支公开状态/引用验证及最终 response sources；只授权、只召回或跨分支凑并集都不计。typed/raw 对应来自同一已验证 Parent/registry 事实，禁止拼剥前缀。用已发布 Atom/Segment 的真实正文与实际引用槽核对已观测 context，不能仅凭 source ID 或 `valid=true`；可复用纯渲染 helper 验证已选单元，不能重跑选择/预算/检索来制造 observed。无关分支失败不得抹去一个本身有效的 Story 分支，也不能把无效分支的证据计入覆盖。
- `topic_page_required_source_retention`：分母为全 gold 每个 `(query_id, required_topic_page_source)`，当前共 9 项，不只取 topic stratum。最终 primary/non-Story 分支的 source_map、实际 context 与已保留 response source 必须指向同一已验证 Child；其 `source_refs` 对 `source_title/pageid/revid/source_content_sha256` 与 gold 的 `source_title/pageid/revid/content_sha256` 精确相符，正文确实留在最终 context；每项至多一次。候选池存在、同名旧 revision、Story source 代替 Page、缺失身份、裁掉正文但保留 metadata 都不能计覆盖。不要为计分改写来源格式。
- 质量只使用每个 query 的 candidate 首个 timed `sample_index=0`；warmup/其余重测不扩大分母或择优。独立 gold 要求不从 observed 补齐，缺样本/缺正文/无适用分母均不得通过。这两项不需要 baseline，沿用既有报告数值格式并明确未执行 baseline 比较；其余涉及调用数、检测 gold、continuation/anchor、REST/SSE、完整引用正确率、关系、性能的 gate 继续 pending。85 例/95 Atom groups/157 mention spans 等审计数量不进入生产常量。
- RED 至少涵盖真实 factory 事务合法而独立 gold Owner 错误、两 Owner packing 后少一个/被拆成两 KB、Page 仅召回但最终丢弃、同名异 revision/hash、伪留 source metadata 而无正文、缺来源/缺样本；增加真正正向的双 Owner 与 Topic/Page 保留对照。复用现有小来源→23 文件→D4→collect fixture；fixture gold 必须显式独立提供，不能照抄本次 observed，冻结正式文件不改。改前采用刚验收的 628 项同字节基线，之后运行本批 RED/GREEN、完整 `test_story_segment_eval.py` 及 `test_story_segment_baseline.py`、`test_rag_eval_deterministic.py` 邻接，D 再独立抽验/冷消费者核对。仍使用 Conda 与 OS temp，不跑真实全量/外部服务。D 审查前不提交、不进入下一批；新范围外根因批量报告 D，不新增监督流程。

本批 fixture 已揭示、D 确认的待修产品根：`packet_policy.py` 的 `TOPIC_STORY_POLICY.sections=(story,plot,lore)` 会排除真实 Topic 的 `lead` Child，而已授权 `story_examples` primary 必须保持 `intent=story`；因此单支主题＋剧情会只留下 Story 并报 `topic_page_shortfall`。本批评分器必须如实判 Page 保留失败。允许语义独立的 Topic primary＋Story 两 KB 请求作为评分器正向对照，但不得强制拆分正式请求或宣称修复原单支能力。E 保留现有失败观测/日志及身份，不新增 receipt；D 在本批检查点后单独定案最小运行时修复，最终交付前闭合。

**最终证据覆盖检查点已验收：** D 在 E 提交 `6a02496876cf70416f653b3e81b3aa30e7db34ec`，三文件 `+422/-29`（生产净增 188 行），原接口/schema/冻结六输入不变；树/index 干净，未合并 main。E 同版本三测试文件 **153 passed**，`C:\Users\HUAWEI\AppData\Local\Temp\covfinal2-164da589.log`，SHA `db8de1789836c8dbfd8f767bee102763ac37d85c0fc8685f05bc2e40d2939e13`。D 独立目标和 baseline/deterministic **51 passed**，OS temp `1999wiki-d-final-coverage-b77e5102d5774ac293edad5a0c8b6888\pytest.log`，SHA `e44c7d6f7ba569672be00861b37301c157c2aec320965a8daedffc456bdd37d1`；同一 bundle 新旧 artifact 报告 canonical bytes 一致，SHA `1bfc2cac3c9be62f517eb6fbfbda63560113b76a6705ee533fee2ba70974329b`。两个全新 Python 进程禁用运行时/配置/网络后，performance/evaluate 仍成功、输入零漂移：OS temp `1999wiki-d-coverage-cold-cf2ef4695fd34d6881ae918fd2816603`，两日志 SHA 分别 `4593b2e08826567d116e6f180deb839a9f93b3da87a2bf5a4b1707bc6aec4569`、`e532cc2e13b387c76f025e5877ca31ecc099b1a53af23a80a25a15bef477d097`。小来源/外部替身的分数仅验证 producer，不能作为真实85题质量；原两 artifact 加本批两项以外仍缺完整 producer。单支 Topic 原失败观测为 OS temp `covred2-a1629237\test_observed_coverage_require0\observations.json`，SHA `000191a6e8719a421598da9f1f4df4043a9ba010a57ce26d38ec3ed8965ae57a`；接受此代码检查点不是豁免该运行时缺陷。

**紧接执行：单支 Topic 主体章节过滤修复。** D 已定位根因，无需另起只读规划轮。E 在上述提交只改生产 `src/rag/packet_policy.py`，以及 `tests/test_entity_packet.py`、`tests/test_story_segment_eval.py`。对明确 `entity_type=topic`、`intent=story` 的 primary policy 不再套用 Story-only 章节白名单，允许该已授权 Topic 自身的 lead/普通正文；复用/派生原 policy，保持名称、source_target、预算、输出方式等其他字段，不重写一套 policy 数据。character/item/psychube/story/page、owner-free general_game 与各 artifact capability 的无关行为不变。绝不更改 Owner/授权/Planner/检索算法，不把 intent 改成 general，不强制拆分请求、不开放跨 Owner 检索。

- 先把现有单支 `Storm Story01` 真 factory/collect 场景改为期望保留 Page 的产品 RED；再最小修改 policy。GREEN 须仍只有一个 KB task、原 `story_examples` 与完整授权，最终有真实 Topic Page 正文及 Story Segment，Page 四身份/引用闭包通过；混入的其他 Owner 不能进入最终来源。正向双 KB 场景继续保留但不能代替它。若只有一个 Page source 而原 source_target 为 2，仍如实保留 available=1 的 shortfall，不降低目标或清除短缺来通过。
- evaluator 不再依赖“自然存在的未修 bug”做负面 fixture：将该单支案例转为正向，调整其独立期望计数；原显式移除正文、缺源、错版本/种类等负面对照继续失败。评分器生产代码不改。补 policy 特征测试证明只有 Topic/story 的章节限制变化，其他字段和实体政策保持。若最小 policy 修正未能穿过真实单支链路，先向 D 给出范围外根因，不旁路现有 gate。
- 使用现有失败观测与刚验收的同字节回归，不重复整轮基线；改后跑两个修改测试文件和现有 `test_rag_topic_scope.py`、`test_hybrid_retriever.py`、`test_retrieval_budget.py` 邻接。D 独立核对后提交。沿用同一 E 模型/工作树与 Conda/OS temp，禁止真实快照、外部服务、媒体、激活及新模块/receipt；不自行合并或进入下一项。

本批邻接回归补充：E 五文件 151 passed + 1 failed、D 独立 49 passed + 1 failed 均只失败于 `tests/test_retrieval_budget.py::test_topic_policy_composition_preserves_story_sections` 的旧章节断言。D 已核对组合算法未变；额外只放行此测试文件将该用例迁移为 Topic/story 与 general_game 合并后的空章节限制，保留策略顺序、source_target 和其他组合断言，不改生产组合/预算逻辑。本批最终四文件；迁移后 E 重跑同五文件，D 独立复验。该迁移落实已批准行为，不降低质量门或新增产品范围。

**Topic 检查点已验收：** D 在 E 提交 `78864b0692120de59ca54b3eb6a936f4db492811`，四文件 `+53/-15`，生产仅净增 2 行，无新模块。E 同字节五文件 **152 passed**，OS temp `topicfinal2-71cb7b32.log`，SHA `843ffac2d07345903b544a8be2ba64fec00f98294990f139c4c334697c0a0829`；D 独立 **50 passed**，OS temp `1999wiki-d-topic-policy-accepted-f916373aa3b949c496ddbf894151061c\pytest.log`，SHA `1ce80068a267d0d98b967bf16b1144968b818b5d975b6a07e2d14a0273036746`。336 组旧新 policy 对照仅 3 个 capability 的 Topic/story sections 改变，所有其他字段/情况一致。真实小来源单支保留 Topic 正文和 Story Atom 引用，Owner 仅 storm/01；原 required=2、available=1 短缺如实保留。评分器、冻结六输入与验收文件字节不变，E 树/index 干净，未合并 main；fixture 的 3/75 与 2/11 仍是 producer 测试数据，不是实际题集质量或发布结论。

**下一小批：复用已安装 Segment 静态索引，落实 S4 的实际运行路径收敛。** 在 E 上述固定提交继续，不另起规划轮。D 已确认安装时 `StoryRuntimeBundle.__post_init__` 建成但丢弃 `by_segment`；每个分支随后在 retrieve、fusion、Retriever 与 expansion 重复遍历整库重建映射，并重算全文字符总量。该批仅消除重复静态工作，不声称已完成 S3 的剩余真实 producer 或达到性能门槛。

- 生产只允许 `src/rag/chain.py`、`src/rag/story_retrieval.py`、`src/rag/retriever.py`；测试只允许现有 `test_story_segment_runtime.py`、`test_story_retrieval_fusion.py`、`test_story_retrieval_budget.py`、`test_hybrid_retriever.py`。保留已批准功能，不修改构建/观测/评测、Planner/授权、schema、gold/阈值、active/v1 路线或外部调用语义，不新增模块、框架、receipt 或全局缓存。
- 在已验证安装边界建立并保留一份只读 ID→原 Segment 引用的派生索引及字符总量；保留需要的原有 Segment tuple，不复制正文/重建另一份业务事实，不允许调用者独立注入索引。原重复 ID、非空 ID/Owner、合法 sequence 与 Atom 闭包检查仍在边界严格执行。将原 `_segment_catalog` 的必要静态验证集中复用；请求内查表，不重新验证整库。
- 统一迁移尚未发布的 retrieve/fusion/expand 内部参数和本仓调用者，让三者使用同一索引；不要增加“原 iterable＋可选 index”的双输入、旧新两套算法或为 E 自身历史测试造兼容包装。外部 BM25/Dense 返回的类型、rank、未知 ID、Owner/关系过滤与契约错误仍每次严格验证。保留原排序、得分、候选上限、seed/邻接顺序、预算、来源/引用和失败分类；expansion 的原上限改读预计算总量，不悄悄收紧或放宽实际预算。允许仅将 expansion 已访问 ID 的线性重复搜索改为保持原输出次序的集合。
- D 改前 fusion/budget/context 三文件 **59 passed**：OS temp `1999wiki-d-segment-catalog-before-f772b3f55436438a88e177598b9df1d2\pytest.log`，SHA `397e486d58efba953a625a1d60e58a6bc6030e4a5d9ac983f84ca3dc3206f30d`。先增加有意义的重复扫描失败用例，再实现；用真实小来源安装后多次检索，证明同一索引复用且请求不再遍历全 Segment tuple/values 重建表或求总量，不能只测一个未接线 helper。纯函数同输入前后完整结果一致，未知命中/越权/坏 rank 等负例及相同 Owner/显式双向边/分支兼容约束保持。新增静态坏输入在安装/建表边界失败；索引不可变且值引用原 Segment。
- 改后完整运行上述四测试文件、现有 `test_story_context_units.py` 与 `test_story_segment_eval.py`，保留真实小来源→安装→collect 的 ranks、最终正文/来源/引用断言。测试只证明算法等价与不重复整库扫描，不把 fixture 延迟当真实生产性能。Conda/OS temp、禁止真实全量与外部服务的边界不变；D 独立审查后提交，E 不自行提交或进入下一项。

**静态索引检查点已验收：** D 在 E 提交 `f5106b5ecf872a48461dcd4d3d1deedda36f77c6`，七文件 `+225/-67`，其中三生产文件净增 10 行；以一个安装期二字段派生索引替换请求中四处建表及整库字符求和，没有兼容双轨或新模块。E 六文件 **238 passed**，OS temp `idxfull-01bb4e3b.log`，SHA `e67efc2c98692533d3d2ac4abbd6a12e9dc2cbb5a3a64b74db00100f14d5b17f`；D 独立 **90 passed**，OS temp `1999wiki-d-segment-index-final-1b1e41bcd14843bd81e5718e00f21930\pytest.log`，SHA `8353ad292687925158fef35ff2ffe4d1472a35f56c99822118784215cf3ef01e`。D 直接执行 `78864b0` 旧代码与新函数：160 组融合、252 组邻接扩展完全一致，完整 retrieve 输出同为 3741 bytes / SHA `fade51f18ffde9d45c9522490777bbb81dd3b6fa56c8735c42e34f7b493a2b94`。真实安装后的重复请求禁止遍历 Segment tuple 与索引，实际三函数复用同一索引；外部命中校验及已有断言保留。最终字节与 D 审查一致，E 树/index 干净，未合并 main；不把 fixture 耗时当作生产性能门已通过。

**S3 下一项先核对计分口径，不改文件：** 在上述固定提交，E 只核对现有观测能否支撑 `fused_segment_recall_at_8` 与 `multi_detail_coverage_rate`，给 D 一份简短消息（不新增计划/receipt）。明确 gold group 的独立分母、同 ID 不同正文/来源版本的拒计规则、固定 Atom→Segment 映射、Top-8 的实际分支级边界，以及多细节“最终上下文可见”与“答案引用成功”的区别；不能把缺映射/缺样本删出分母、重跑检索/packer、从 observed 补 gold 或复用旧 fixture 平铺字段。D 同步核对冻结 gold/source/mapping 和 Spec；只有口径与真实接口一致才放行代码。仅阅读现有模块/小 fixture，不启动新 E、真实全量或外部调用；提交的原 56 gate 与阈值保持。

**上述 Recall 口径已由 D 定案，放行实现：** E 在 `f5106b5` 仅修改 `src/rag_eval/story_run_observations.py` 与 `tests/test_story_segment_eval.py`，实现原 `fused_segment_recall_at_8`、`multi_detail_coverage_rate` 两项 producer。共用现有 artifact loader 和正文验证，原 collect/CLI/schema/56 项九字段报告、已有四项 producer 的口径及字节行为保持；不新增采集字段/模块/receipt，不改 runtime、runner、baseline、gold 或阈值。

- 分母固定来自每个 `(query_id, group_id)`，所有 required groups 参加融合 Recall（现有 95：direct 92、anchor 2、continuation 1）；multi-detail 仅取 `stratum=single_story_multi_detail` 的 groups（现有 20）。数量动态计算；缺样本/缺映射/错版本不删分母，每组至多贡献一次，零分母不通过。只用 candidate 首个 timed sample，不能择优重测。
- Gold Atom 必须与已验证候选 Atom 的 ID、完整正文 `evidence_sha256`（仅 NFC/换行）及精确 source title/json_path/source content hash 相符，再由已验证 Atom→Segment mapping 与 Segment 成员/Owner 机械推出 relevant Segment；同 ID 异正文/来源不能计覆盖，不能借用 `fused.matched_atom_ids` 排除 Dense-only 的有效命中。只检索引用既有输入，不要求整个 candidate Child 文件与旧 gold Atom artifact 同 hash，也不能从观察分数回填标签。
- Top-8 是每个实际 KB 子任务的 Story 检索调用返回的 `candidates.fused[:8]`，保留原位置；单 KB 的多 Owner 比较共用这一个窗口，不是每 Owner 八条。核对既有最终 plan/authorization/span 归属和行 ID/Owner，同一原 query 的合法分支命中按 group 去重汇总。这是实际执行单元 Top-8 的 query-group Recall，不宣称存在 runtime 没有产出的 request-global 排名。禁止重新融合、跨分支拼排 8N、用 seed/selected/扩展代替 fused，或删除坏行后以 rank 9 回填。重复/未知 ID、Owner 矛盾等不完整输入按原严格校验拒绝，不能提升有效候选排名。
- 多细节只看全局引用重绑定后的 `branch.context + selection + source_map` 与固定 Segment/Atom 完整可见正文闭包，不把候选命中当打包保留。将原 body helper 中共享的完整块/slot/heading/顺序检查抽出复用；旧 Owner/Page 的最终 public 来源及答案校验门留在原外层，新 Recall 不要求 LLM succeeded、回答包含引用或 response.sources 未裁掉。该 context 是最终 packer 文本，不等于完整模型消息或实际 API 调用证明，不能据此声称调用数/延迟通过。
- 测试在 collect 前独立指定小来源 gold groups，验证真实 factory 接线；纯评分正反例覆盖第 8/9 位、单组替代 Atom/多分支去重、无映射/错正文/版本/path/缺样本仍保持分母、Dense-only、召回与 packing 两阶段不互相代替、LLM 后续失败/引用变化不改已打包证据分子。原四项指标及所有显式负例保持，两个冷消费者继续禁止重新执行检索/packer/模型；可提取纯正文渲染用于验证已观测块，不生成新选择。改前沿用已验收 238 项与原 baseline/deterministic 同字节证据；改后跑目标 RED/GREEN、完整 eval/baseline/deterministic 三文件，D 独立验收后提交。只说明新增两项真实 producer，其他未测门仍不通过，不触发全量/外部服务或新增监督层。

**Group Recall 检查点已验收：** D 在 E 提交 `7b6c5fd010364821c7021065f03ca8e96a902eba`，两文件 `+338/-12`，生产净增 106 行，无新模块、schema 或采集字段。E 同字节三文件 **154 passed**，OS temp `grpfinal-bee585e0.log`，SHA `0cb9efc735bb0181b85eeeef372c623a546987748decf2dbde18906cd8a20e59`；D 独立 **52 passed**，OS temp `1999wiki-d-group-recall-final-bb15049bdb784c5e91393c2c2e840c78\pytest.log`，SHA `cc292c645ae8eca496cc5b6e4734ff7bab587a86224477e7c908ac89e31b54a7`。两个全新 Python 冷消费者在禁止配置/运行时/packing/网络调用时正常完成，输入零漂移；D 与 `f5106b5` 旧评分函数直接对照，既有四项 producer 行保持一致。Owner 索引由评分入口构建一次并显式共用。独立小来源测试的 6/102 与 2/22 仅证明两个 producer 实际接线及负例有效，报告仍为 `no_go`；目前六项 producer 已具备本地实现，不代表真实 85 题六项通过，其他 50 项仍待真实输入与实现。E 树/index 干净，未合并 main。

D 本轮只读核对确认：冻结 baseline 是 retrieval-only，保留 85 例 RRF 检索/最终上下文和原始 Dense cassette，`generation_calls=0`，不能充作原始 BM25 或回答/端到端耗时基线；190 条等价记录在两阶段均无匹配（每阶段 48 条缺 source ref、47 条来源版本不符）。原字节和匹配规则保持，不重开 D0，不以 candidate 分数自比。后续评分必须按真实来源和适用分母计算，缺少独立输入的指标继续不通过。

**下一项只读范围：** 同一 E 在 `7b6c5fd` 核对冻结 baseline/equivalence 能否支持 `final_evidence_recall` 与 `middle_late_final_evidence_recall_delta`。仅明确最终上下文阶段、独立分母、身份/等价闭包、必要 CLI 输入及现有 matcher/producer 复用；不修改文件、不新增文档或 receipt、不重采集、不扩展其他指标。D 同步核对后放行最小实现。

**只读核对已完成，放行两个最终上下文指标：** D/E 均验证冻结 baseline business identity、85 个 case hash、gold/阈值/等价关联；现有未改 matcher 从历史两阶段结果复现 190 条等价记录。没有同 Atom ID 或同来源版本候选，故该次只读复验不需要额外 Atom needle。有效历史 Recall 为全体 `0/95`、中后段 `0/6`，不表示门通过。E 在 `7b6c5fd` 仅修改 `src/rag_eval/story_run_observations.py`、`scripts/evaluate_story_segment_rag.py`、`tests/test_story_segment_eval.py`；不改冻结文件、matcher/capture、runtime、runner 或阈值，不新增模块/框架/receipt。

- `evaluate` 增加四个必填参数：`--baseline-receipt`、`--expected-baseline-receipt-sha256`、`--equivalence`、`--expected-equivalence-sha256`。历史输入先用外部预期 SHA 固定，再核对 schema、business/case hash、query 与 gold/阈值关联、阶段/目标/唯一性/计数闭包；business identity 从已固定 receipt 重算，不另立可编辑参数。既有 D 接受的精确历史字节是本批 baseline 来源，不在消费者中导入 capture/重开 D0/重采集或复制 matcher。baseline 缺项或身份矛盾必须拒绝，不默认零；历史代码身份保留历史值，不要求旧 capture SHA 等于当前脚本。必要报告输入身份与输出路径保护一并贯通。
- 在原 group 遍历中复用已验证 relevant/visible 集合和一次 Owner 索引，追加两行，不重做检索、fusion、packer 或正文评分。全体按每个 `(query_id, group_id)` 计分；中后段仅按冻结 `query_type` 的 `middle_fact/ending_fact` 选组，不按候选分数或查询 ID 选组。两个阶段分开，baseline 只取 `final_context`，成员 Atom 命中 OR；候选缺样本/映射/错版本不删分母，跨合法分支每组至多一次。最终证据须达到 0.90 且不低于 baseline；中后段 baseline 低于 0.90 时至少提升 0.10，否则不退化；复用原 gate 算法，零分母不通过。原六项 producer 行保持一致。
- 测试先独立声明小来源 gold 与历史上下文，再 collect 候选，不能从候选命中反填 baseline；共享精简的本文件 fixture 即可，不新增大体量测试框架。覆盖检索命中但最终未保留、替代 Atom/重复组计数、baseline 非零的相对门与 0.90 分支、缺失/错阶段/错目标/身份漂移拒绝、候选失败/缺证据仍保留分母、零分母、原六项字节等价及两个冷消费者禁止执行链。改前沿用已验收同字节 154 项；新增有效 RED 后实现，再跑完整 eval/baseline/deterministic 三文件及必要定向测试。Conda/OS temp、无真实全量或外部调用的边界不变；D 独立验收后提交，E 不自行提交或进入后续指标。

**最终上下文 Recall 检查点已验收：** D 在 E 提交 `0da69c33b7d985f0c468087e95ae6b8af8aa3a4a`，三文件 `+302/-18`，生产净增 108 行，无新模块/框架/receipt。E 同字节三文件 **155 passed**，OS temp `finfull-1b0384c6.log`，SHA `345af3816d28ade53f471550869956704237b2d8b42f6828bc2f6bbe32ecfac8`；D 独立 **53 passed**，OS temp `1999wiki-d-final-recall-ad8dd4f0d53a4d709e44e0aae8953191\pytest.log`，SHA `a28f51b1d22d09fabc2ed075cc60024437379799d9b0145808db0a761ab51f2b`。D 两个全新冷进程禁用 16 个执行/检索/packer/模型/网络调用入口，28 个输入文件零漂移，未导入 capture；OS temp `1999wiki-d-final-cold-1788618793399` 的两日志 SHA 分别 `a18c6c0cbd7dd1b9e5e4e8c6867de8e3efbb17e1f68256372ea77cb899383c73`、`d7cd91310520dcaba1df939805cb03047d36594ff55a1832c1f054cc7df8fbf0`。D 直接执行 `7b6c5fd` 旧评分函数，原六行 canonical bytes 一致，SHA `c3745847c4100b795bfa6d28cc550b911862210faad4a096e0da1eb23596295c`。小来源最终证据 7/102 对历史 4/102、中后段 4/10 对 2/10，报告仍 `no_go`；已具备八项本地 producer，不声称真实题集通过，其余 48 项仍待验证/实现。E 树/index 干净，未合并 main，冻结输入与运行时不变。

**下一项先收敛旧评测路径，只读：** 同一 E 在 `0da69c3` 核对 `story_segment_runner.py` 中旧 `evaluate_offline_candidate/_evaluate_offline_core/_contract_observations` 及其专用依赖的实际调用图。区分当前 collect/evaluate/artifacts、候选构建仍使用的共享功能，与仅被旧 synthetic 测试使用、可产生自比 baseline/假观测的过渡入口；列出可删除闭包及必须保留或迁移的真实回归，不以删测试消除待实现质量门。此轮仅消息报告，不改文件/计划/receipt，不扩展其余指标，不新增会话或执行真实全量。D 独立核对后决定最小 S4 实施范围，避免继续叠加新旧两套评分事实源。

**S4 退役范围已核定，放行同批收敛：** D/E 调用图均确认旧 synthetic evaluator 与旧性能回执链无当前产品消费者；旧最终报告始终强制 fake/no_go，不是已发现的激活绕过，但内部自比 baseline 和从 gold 抄入的布尔/调用数不是真实质量证据。E 在 `0da69c3` 只修改 `src/rag_eval/story_segment_runner.py`、`tests/test_story_segment_eval.py`、`tests/test_rag_eval_runner.py`、`tests/test_rag_eval_deterministic.py`，一批完成下述删除与测试迁移，不另设兼容模式或新模块。

- 删除旧六定义 `evaluate_offline_candidate/_evaluate_offline_core/_contract_observations/_validate_case_evidence/_validate_capacity_evidence/_load_equivalence`、其专用字段表与失用 helper/import/export；删除无仓内调用的三个 `Verified*RuntimeSnapshot/VerifiedShadowBuildReceipt` wrapper 类、`_current_active_runtime` 和三个旧 resolve/load wrapper。真正 `runtime_artifacts` resolver 不变。连同删除旧性能支系 `_performance_metrics/_validated_lane/_utc_now/_machine_profile/_validate_performance_receipt_structure/build_performance_control_receipt/VerifiedPerformanceReceipt/_parse_utc/load_and_validate_performance_control_receipt` 及其专用常量/导入，不把它们搬到测试 helper 中保存另一套实现。
- 保留当前产品可达的 15 个定义、真实安装观察的 `execute_installed_story_query` 既有重导出，以及 `evaluate_fake_dense_fixture/build_story_segment_evaluation_report` 的明确 fake/ineligible 纯展示边界；后两者仍供旧 D2 格式和 reporting 测试使用，本批不改变打包或继任 handoff 职责。共享 `_observation` 的 `baseline` 改为必填关键字，消除默认 candidate 自比；当前八项调用已显式传值，其他行为/字节保持。运行时、observations 生产、CLI、counterfactual、冻结 gold/threshold/D2 与八项报告均不改。
- 删除或迁移旧入口专用的合成 wire/token/capacity 断言和 fixture；独立输入 SHA、禁止预装 metric、Owner/顺序/origin/span 伪造、重复样本、原语类型及缺测 fail-closed 必须落到既有真实 collect/loader/安装链或纯 gate 测试。原未实现的 48 项仍不通过；不能把旧合成正例变成新 producer，也不能删 gate 解决缺测。旧性能百分位/逐样本求和只保留纯算术回归（复用已有 `_percentile`）及真实 projection 的区间命名/未测阶段断言，不凭相加样本制造 TTFT 或流水线已观测结论。零 warmup 拒绝迁到实际 `collect_story_run`，验证发生在配置/文件/运行时调用前；迁移旧 CLI 精确参数表为当前四命令，保留必填和无隐藏 collection flag 约束。消息中交代旧测试→保留/迁移/退役关系，不新增矩阵文档/receipt；发现实际功能缺陷先给 D 根因，不放宽断言或扩大生产范围。
- 改前沿用同字节已验收 155 项，补查三个通用 eval runner/reporting/scoring 文件的特征基线；已确认旧 CLI 参数断言与当前协议不符，明确记录为迁移对象，不回滚产品来适配它。改后完整运行 eval、baseline、deterministic、runner、reporting、scoring 六文件，再跑现有 Story request-plan/authorization/public-contracts/retrieval-fusion 回归；D 独立复核当前八项及两个冷消费者的新旧完整字节、调用图和保护文件。删除导致测试数降低须解释对应退役项，不以数量不变或净删行配额为目标。Conda/OS temp、禁止真实快照/外部服务/媒体/激活边界不变；D 验收后提交，E 不自行 stage/commit/merge 或进入下一项。

**S4 退役检查点已验收：** D 在 E 提交 `5ed8fc0ffa3c3ebf38fbfb4f8edc53ccaa39d3f3`，四文件净减 2,046 行；生产 runner 从 1,672 行降至 495 行（净减 1,177），删除 22 个旧链定义与 2 个专属 helper，16 个保留定义 AST 不变，仅 `_observation` 取消默认自比。E 六文件 **167 passed**、四 Story 邻接 **256 passed**，OS temp `s4full-a27d35cc.log` / `s4adjacent-19a7f3f0.log`，SHA 分别 `8b8093998c3772f368ccef06861f19aca9f4665afe8f2f66f03221e5c5017601` / `281f62cf260daeefb20f39c4119ffe816ff1d46c177b232c8cedd3487a549c75`。改前 193 个实例中退役旧 wire/合成测量 29 个、迁移纯数学 3 个，净减 26；CLI/warmup 一对一迁移，质量门和真实安全回归未删。D 独立 **91 passed**，OS temp `1999wiki-d-legacy-retirement-aa65fde6c30c4131a05ac9938522df52\pytest.log`，SHA `1263864acf437bb773db8e892019841c483d07e684efb1de5c5c5f7e7a68ba1d`。D 冷进程禁用 16 个执行入口、28 文件零漂移，两个完整报告与 `0da69c3` 原字节一致；OS temp `1999wiki-d-retirement-cold-1788622730790` 两日志 SHA `76d1bd7d27c1890c60527548b44a2840aca3d338554594f3aaa8838eb65bad9c` / `bd7674dbe7e4f74e381f0a4a3f5615f07e344fe77622cbc7726d747cb819bb79`。当前八项指标不变、其余 48 项无证据不通过；E 树/index 干净，未合并 main。旧实现保留在 Git 历史，不重新创建兼容入口。

**S3 后续按证据家族收拢，先只读：** E 在 `5ed8fc0` 将剩余 48 个 gate 按当前输入足够、缺真实执行观测、缺独立标签/历史对照、只在 D 真实构建阶段有证据分组；列出下一最小连贯实现组及精确数据来源/缺口。不得为了逐项给进度而复制 48 个 scorer，不能把 schema 自校验等同正确率、内部区间等同 TTFT、当前题集输出反填 gold。仅阅读现有阈值/观测/冻结标签与代码接口，给一条紧凑消息，不新写矩阵文档、不改文件、不运行任何采集或新任务；D 同步核对后放行。当前清理完成不等于所有 S3/S4/S5 或真实质量完成。

**2026-09-06：放行同一证据家族的三门实现。** 起点 E `5ed8fc0`，仅修改 `src/rag_eval/story_run_observations.py` 与 `tests/test_story_segment_eval.py`，实现 `atom_citation_closure_rate`、`owner_gate_unauthorized_rate`、`story_duplicate_body_rate`。撤回只读盘点中“11 项输入已齐”和排名四项建议：历史 `retrieval_at_k` 是 RRF 而非原始 BM25；semantic 子集未冻结；gold 的 Story mention spans 不等于全体子任务 SourceQuerySpan；4/5/32/33 个显式 mention 被拒绝授权不等于 detector 阴性。这些缺口不得用合成标签或改阈值填补。本批将必要观测与消费者一次接通，不另建准备批、矩阵、模块或回执。

- **实际观测缺口必须补齐。** 当前 selection 仅保存扁平 ID，公开 sources 没有 `content/content_hash/source_refs`；从 canonical bundle 重建 span 只能作为独立期望，不能冒充实际 span/source。复用 `_project_branch` 已持有的实际 `StoryContextSelection.context_units/citation_sources`，记录必要的 unit/span/来源字段；正文仅保存从实际文本计算的哈希，不复制整段正文。保留原局部 citation ID，以现有 `(Segment, Atom)` 和全局 source_map 验证一对一重绑；不重新分配 ID 或再次调用执行/packing。观测契约升级为严格 v2，无旧 v1 自动填充/转换；旧文件保留历史身份，当前小 fixture 通过实际 collector 生成 v2。不改 runtime/public/CLI/snapshot schema，不把 selection 的局部来源说成已观测的最终 HTTP 完整来源。新字段直接来自原对象，已有扁平 ID 必须与它们一致，不能成为第二套独立声明。
- **共同计分边界。** 每题只使用 candidate 的首个 timed sample，按实际 KB 生成上下文分别核对；完整样本数仍由现有 loader 保证。原始 selection、slot 和正文出现位置先构成计数全集，再验证闭包，不能用 `_retained_branch_sources/_visible_story_segments` 的成功子集作分母。明确的失败保留失败，不完整证据使用现有缺测不通过或拒绝无效输入，不能静默跳过；已观测空与 `None` 不混用。零分母仍不通过，不制造一个成功样本。已实现八项 producer 的数值/行为保持，其他 45 项仍未完成。
- **Atom 引用闭包。** 分母是已观测选中 unit 中应有的非空 canonical Atom 出现次数，不将同一个 Atom 的 span、slot、marker 三重相加。逐项核对实际 unit 基础文本哈希、code-point span、Atom 哈希/来源/Owner/Parent、局部 source 与全局 source_map/public 可见字段、实际完整正文及追加一次的 `[Sxx]`。缺 span/source/marker 或错正文保留预期分母且不得计成功。多余/重复 slot、无法归属的事实正文等不能因不在声明 ID 内而被忽略；无法建立完整全集时门不通过。不得要求最终 LLM 答案使用每个引用；本门证明 packer 与引用闭包，不证明最终回答质量或完整模型消息。
- **Owner 越权率。** 限制 Owner 的已授权 Story 检索，分母是实际 `owner_atom_ranks` 与 `owner_dense_ranks` 指向的返回行总数，保留通道次数，不按 ID 去重；由原始 rank、固定 Atom→Segment、canonical Owner 和唯一已验证授权上下文计算越权分子。不能用关系过滤后的 eligible、fused Top-8、selected 或最终来源缩小分母；正确被 Owner gate 排除的原始 Atom 不算泄漏。原始 Dense 元数据必须与 canonical Owner 一致；未知 ID/rank 不跳过。open_story_domain 的空 allowlist 不等于拒绝所有 Owner，也不贡献受限检索成功样本；拒绝分支返回 Story 证据仍失败。缺完整检索观测不得报告零越权。
- **重复正文率。** 分母是同一实际 KB 上下文中 Story unit 出现实例的所有无序对，保留位置/次数；重复同 Segment 或同来源 Atom 被 Segment 与独立 Atom 再次封装的对计入分子。遵循 Spec 的同来源身份原则：不同 Story、不同规范来源路径的合法相同对白不按文本哈希去重。不跨独立回答分支或重复 timed sample 比较。复用现有纯渲染规则识别实际块，保留可证明的重复实例；不得仅对已去重的 selected ID 求组合数。未知/残缺正文或无法闭合位置不能变为“零重复”，也不为解析任意 Markdown 建立通用框架。
- **一批测试与审查。** 沿用已验收 167 项评测与 256 项邻接基线，先增加实际 collector 到三门的 RED，再实现并运行完整六个评测文件及必要实际安装/引用重绑邻接。共享本文件小来源 fixture；覆盖双 Story 全局引用、错/缺 span/hash/source、重复及无引用正文、合法同文异源、Owner 原始/过滤/关系/融合顺序差异、open/denied/空/缺测与零分母。正常历史八行保持同值；两个冷消费者禁止运行时/检索/packer/模型/网络，v1 不得被静默解释为 v2。若实际接口不足，先报告精确缺口，不扩大文件范围。Conda `1999wiki`、OS temp，E 不自行提交；D 独立验收后形成一个检查点。禁止真实全量/旧 Step 6/Build A、embedding/Milvus/SSH/媒体/激活，不修改冻结 gold/threshold/baseline/D2。

**三门检查点已由 D 验收：** E 提交 `f483e20a48ec67923eb94acafd0b2ac0bed11e67`，仍仅两文件 `+563/-7`（生产净 +268、测试净 +288），无新模块/框架/回执；观测严格 v2，既有七个评分/匹配 helper 未变。D 曾独立复现 Dense raw 越权行被 Owner rank 子集隐去的 P1，最终用三行校验要求 Dense Owner 引用全覆盖实际返回；关系过滤仍可缩减 eligible，正确排除原始行的正例限定 Atom。E 最终六文件 **168 passed**、受影响目标/fusion **40 passed**；本批原邻接 **267 passed**。D 原整组 **99 passed**，P1 后最终受影响组 **41 passed**，日志 OS temp `1999wiki-d-body-final-3a2c56a173e84f86b01059028795ef71\pytest.log`，SHA `41eb128d967b8770de850c0cfa39ba414a4090d2a9db952aa5eaaed2cecaed23`；E 最终六文件日志 `b3p1full-d7fc77dd.log`，SHA `39880d00c17891a64ca6251c1cfb49efca463e4a574fe03190b83af71b3f8cce`。

D 两个全新冷进程禁用 16 个执行/网络入口、29 个输入零漂移，历史 v1 原字节保留且拒绝转换；完整正常报告与 P1 前一致，原八行 2521 bytes / SHA `c777884a92e7afce8968b0042a48e08ece6326f3a966e03196085b358b7d13ff`。独立原反例已拒绝，完整越权返回计入失败。冷证据位于 OS temp `1999wiki-d-body-cold-1788634462062`，evaluate/performance 日志 SHA 分别 `0b7e8044f3d124e1a5253ca70e01bca988702b7f07f504fe2d6482b076e65a1a` / `2d66218003052c7d85730c26d4d4d032ed5d6b34116ebeabfeb53708bf8d472d`。小 fixture 三行 `19/19`、`0/47`、`0/24` 仅证明真实 producer 接线；现在 11 项有本地 producer，其他 45 项缺测不通过，报告仍 `no_go`。最终生产/测试 SHA 为 `7e569d410361802227a3ac9af4fa0aca08a4ca2ea497bb6d0b394a57ddcdf191` / `a15f0ec7e270229a475f377e49f39167fe4f786037a6b0af74238d070dc40ad1`；E 树/index 干净，未合并 main，无真实构建或外部操作。

**下一证据家族先只读，不改文件：** 同一 E 在 `f483e20` 核对六个调用/扫描门：`request_detector_calls`、`dense_embedding_calls_per_knowledge_subtask`、`reranker_api_calls`、`answer_scope_added_api_calls`、`ambiguous_story_detection_retriever_calls`、`story_query_time_full_scan_count`。将各门的独立分母、实际调用入口、现有 trace/counter、缺测/失败分支与尚缺观测写成一条紧凑消息，提出可共享的最小接线；不得从配置关闭、返回成功、预置零值或静态代码扫描宣称运行期零调用。优先复用现有同次结果/RequestTrace，不另设通用 observer、重复计数器或六份 scorer；若某门需要未有的观测，应明确缺口而非强行实现。此轮不写矩阵/计划/receipt、不跑采集/全量/外部服务，不改阈值、runtime 或启动新任务；D 独立核定后才放行实现。

**2026-09-09：只读结论与最小 BM25 优化批。** D/E 均核对实际调用边界：Detector receipt 不是调用计数，Story Dense session 只记录成功向量且未覆盖主 Child 路径，rerank 阶段进入不等于 API 调用，AnswerScope 缺同包两次归一化观测；错误检测七类独立输入未被当前普通请求 collector 覆盖。六门暂不增加评分行，不将静态检查或单测通过冒充真实题集通过。后续调用观测仍优先沿现有 RequestTrace 接线，不新增通用 observer。另确认 `LocalBM25SparseIndex.search` 每个非空查询枚举全部 `doc_terms` 并重算文档长度；已安装 Story Atom 确实调用此索引，原 Segment 静态索引回归没有覆盖这一遍历。先修算法根因，不用一个预置扫描计数遮掩它。

- 当前合法起点为 E `f483e20a48ec67923eb94acafd0b2ac0bed11e67`、干净树/index；旧 `c81d336 + 11 dirty files` 仅是历史收敛起点，不是当前恢复门。仅允许修改 `src/rag/sparse.py`、`tests/test_sparse_bm25.py`、`tests/test_story_segment_runtime.py`。同一现有 E task 执行，模型/速度保持最新批准设置，不新建会话、不恢复旧 Step 6/Build A。
- 在现有 build/load 阶段生成 term→文档位置倒排表和文档长度；query 只访问查询词的 postings 与命中文档，按原文档位置稳定处理。复用已有词频，不复制第二套 TF 或引入新检索引擎。保持 Analyzer/参数、重复查询词的加权顺序、浮点评分、同分顺序、无命中返回空、既有零分补齐与 top_k 切片行为。补齐只按所需位置读取，不计算未命中文档的词频；高频词的合法 posting 命中可能覆盖全部文档，这不等同于无条件扫描全表，不能据此宣称最坏时间恒定。
- 保持 records/文件 schema、Analyzer 身份、保存字节及 load 接口；倒排表是已安装索引的派生内存状态，不写新 sidecar、manifest 或兼容分支。成功重建统一替换状态，失败仍保留旧索引可用，空重建不能残留 posting。不得修改 BM25 召回/融合策略、授权、trace、观测 schema、冻结 eval 文件、构建器或生产产物。仅此优化不增加任何质量门的“通过”声明。
- 先跑现有 BM25/Analyzer/影子小 fixture 回归，再补能暴露全表遍历和无关文档读取的 RED；在实际安装链上扩展既有静态索引测试，证明真实 Atom 检索仍被执行而非替身返回。GREEN 必须覆盖 legacy/中文、重复词/同分/无命中/补齐、保存加载、空/失败重建；用独立旧公式的小型差分覆盖分数和完整返回顺序，原实现只保留在 Git 或测试 oracle，不能在产品保留双路径。复用既有 fixture，不为案例创建通用测试框架。
- 改后跑三项 BM25/Analyzer/影子文件、完整 Story runtime/fusion，以及必要 observations 已安装链邻接；D 独立对照旧提交评分/文件字节、查询访问范围及 scope 后提交。只用本地 fixture/Conda `1999wiki`/OS temp，禁止真实快照、LLM/embedding/Milvus/SSH/媒体/激活。E 不 stage/commit，不进入其余五门或新采集批；异常在同一范围内根因明确时最小修复，越界先回报 D。

**BM25 检查点已验收：** D 在 E 提交 `697c6ab8ddd8d4039cb3950fcf9cd0ecd8e90c0d`，三文件 `+153/-4`，生产净 +12 行，仅修改原索引类的初始化/build/search，13 个其余定义 AST 不变。E 原三文件 100 项通过；有效 RED 三处全表/无关读取失败；最终三文件 **108 passed**、完整 Story runtime/fusion 与观测邻接 **100 passed**。最终两日志为 OS temp `bmfull-ff8ee450.log` / `bmadj-6bdfe392.log`，SHA `a17eb8cef9408416146b661e327370a14972c3ea6be3b325dd600d8427697993` / `312f91914f56e3f491b64128783102d051a70a8b808e383af17c716f0806a1ee`。D 独立 **121 passed**，日志 `1999wiki-d-bm25-c6a078a28c4742f4b2a6266987e25cbb\pytest.log`，SHA `46e81efff9fa3709c35b9d79398427a0beeef2b73c078c8db56cf8f9fb6c0feb`；与 `f483e20` 实际旧类比较 **3,780 组完整查询结果、36 组保存字节完全一致**，差分日志同目录 `differential.log`，SHA `526afbb18c4a9b27c2b56cac372eff84743fdc2e1a9dbe86ad8d958658edace6`。2,000 文档/单命中小例中词频读取从 2,000 条降至 1 条，补齐结果仍相同；不外推整体延迟或真实扫描门通过。最终生产 SHA `e66200bfe4d266d0465bc8819650058d1da57b26570f856af13cbca7fc182d19`；树/index 干净，冻结四输入与 observations 字节不变，未合并 main、无外部调用。

**下一项仍限定为只读具体接线：** 同一 E 在 `697c6ab` 核对主 Child 与 Story supplement 是否对同一 KB 的相同 query/model 重复调用 embedding，以及共用现有 `StoryDenseQuerySession` 的最小接线点。特别区分 `_RuntimeStoryRetriever.search` 返回固定主来源的替身与实际已安装 `Retriever.search`；不能用前者证明真实主路径调用数。按实际调用图说明正常/两个不同 query/依赖失败/并发子任务的作用域，并提出沿现有 RequestTrace 记录实际尝试（含异常）的最小方案及测试位置；不要增加全局缓存、observer、另一套计数事实源或宽松 duck-typing fallback。此轮仅一条紧凑报告，不改文件、不运行测试/采集、不新写计划或 receipt，不扩大六门分母、不进入真实构建；D 独立决定下一批统一实现与观测边界。

**共享 Dense 只读核对完成，放行单一修复批：** D/E 均确认真实 candidate factory 使用同一个已验证 adapter，但主 Child 直接 embed、Story supplement 自建 session；当 `dense_query` 为空或等于 `normalized_query`，且主分支确实进入 Dense 时产生重复调用。非空不同 `dense_query` 是两个合法输入，不能为去重改写 Planner。E 起点 `697c6ab`；生产只允许 `src/rag/{chain,retriever,story_retrieval,tracing}.py`，测试只允许 `tests/{test_retriever,test_story_retrieval_fusion,test_story_segment_runtime,test_rag_tracing}.py`。现有 helper fixture 可在这些文件内精确迁移新参数/adapter，不保留另一个产品调用路径来适配失真的替身。

- 在现有授权与分支校验完成后、主检索之前创建当前 KB 局部的 `StoryDenseQuerySession`，显式沿主 search→typed Child Dense 和 Story candidates 共用；保持两个 typed search 的过滤、结果和执行顺序独立。安装链使用同一已验证 adapter/model，拒绝交叉借用；只在交接边界检查，不反复加载 snapshot 或增加 receipt。既有独立候选 helper 可显式接收可选 session，未提供时保留独立调用的一次局部 session；已安装 Story 路径必须提供，不能基于反射/异常猜测切回 direct embedding。未使用 Story session 的 active v1 调度与原 capture 接口保持不变。
- 一个 KB 只缓存本次执行的至多两个 query 尝试，同 query 成功复用原 immutable vector，不复用检索结果；新请求或不同并发 KB 各自创建 session。失败/非法向量也占已尝试 query 的名额，同次再请求同 query 不再 dispatch，保留原失败分类；第三 query 在 provider 前拒绝。不新增全局 cache、retry manager 或独立计数器。既有成功向量记录与 `embedding_call_count` 从同一尝试状态导出，避免成功列表冒充尝试数；候选 `query_vector_identity` 必须属于本次 Story query，不能再取共享 session 的首条 Child 记录。
- 依赖异常仅沿现有精确 `StoryDenseDependencyUnavailable`/`OpenAIError` 翻译边界处理。真实主 embedding/typed Dense 失败按既有 `RetrievalExecutionError` 表达 KB `failed`，不伪造已验证主证据、额外重试或生成；主分支完成后 Story 第二 query 或 typed search 依赖失败，保留真实主证据与现有 supplement partial/failed 规则。非法向量、Owner、adapter/model 和其它契约错误保持硬失败，不能扩大 catch 当作依赖降级。不改变 Planner、授权、AnswerScope 或公开 outcome 聚合算法。
- 复用同一个 RequestTrace：chain 显式传给 Story retriever，再交局部 session；主 search 也不再丢失 trace。只在实际 provider dispatch 处产生一个尝试 span，现有 finally 保留异常；cache hit/限额预拒绝不产生适配层调用尝试。本批 span 证明适配层 dispatch，不冒充 SDK 内部 HTTP 重试/分段的完整请求计数；SDK 内部行为尚未观测，不修改重试策略或降低最终 API 门含义。最小安全归属包含当前子任务的不可逆身份、query SHA、来自已验证 bundle 的 model identity 和固定用途；不得记录原问题/明文 query/向量/异常正文。实际 `T01` 等含大写的 subtask ID 不得被错误套用当前小写 token 正则；可使用 UTF-8 SHA-256 归属，在既有安全属性函数中严格验证哈希。现有 observations v2 自然投影实际 spans，不新增 schema、scorer、observer 或重复导出；NullTrace/采集异常仍无有效测量，六门不因本批局部 trace 自动通过，未观测的非 Story KB 不补零。
- 测试先保留现有四文件基线，再增加真实 `_observation_factory_fixture`→`_build_lanes` candidate Retriever 的 RED；只替外部 provider/typed-search 边界，不用固定主 sources 或 generic-search 空返回证明 typed Child 调用。覆盖 Character/Topic supplement 同 query 一次、两 query 各一次且 Story 向量身份正确、主与补依赖失败分别归类、错误向量/交叉 adapter/model 拒绝、第三 query 拒绝/失败不重试；两个并发 KB 用有超时的同步点验证作用域隔离，并验证跨请求不共享。已有单纯授权/预算 fixture 仍只证明原职责，不把它们升级为实测次数证据。
- GREEN 后跑完整四个允许测试文件及现有 eval 中实际安装/collect/Owner-Topic-正文观测邻接；D 独立验收接线、异常、并发归属和既有正文结果后提交。无新模块/测试框架/矩阵/回执；无真实全量、旧 Step 6、LLM/embedding/Milvus/SSH/媒体/激活，不改冻结输入、observations 或 vectorstore adapter。超出此修复范围先回报 D，不自行进入其它调用门或重启任务。

**共享 Dense 检查点已验收：** D 在 E 提交 `d35a4d1616f3e94cea9497dd66215f11ecb83658`，八文件 `+483/-64`，生产四文件净 +65 行，无新模块/框架/回执。E 有效 RED 六项；最终完整四文件 **146 passed**、真实安装/collect/Owner-Topic-正文观测邻接 **15 passed**，日志 OS temp `dsfull2-ba60eb36.log` / `dsadj-02dbb2b4.log`，SHA 分别 `11589454c758a2e44865ea4239e57f136bcc2b18985dce6286c54e7536c2d977` / `81cea2e35d457e22e3cf59e21a1fe9544b6ce69dd12d22c84163d93e4c350c2d`。旧夹具缺 Segment 索引/adapter 与两处新测试对象访问错误均只在允许测试内修正，最终没有未闭合失败，未增产品兼容路径。

D 独立 **94 + 13 passed**，后组覆盖最后修改节点、非 Story active v1 与历史 Dense cassette；两日志为 OS temp `1999wiki-d-dense-tests-25769055c7f041af9536b6c6b08cd87b/pytest.log` / `1999wiki-d-dense-final-f5ad0570e93b4cea8e11974f868b1789/pytest.log`，SHA 分别 `1318c08e9f6a99b4048bc1ee7f7d6351c9c7e9f81d296acf20361c822688dc86` / `6d1c65bec9bb224044dfb773035fadffec9700ba4426e5f0f0f0cab0cbc388b6`。D 在**同一实际安装的小来源**中以内存加载 `697c6ab` 旧方法和当前方法对照，除 trace 外完整规划/响应/候选/正文/来源投影一致，SHA `d477273677f1daacf09468780474ef0581025cc642958a939908a248d0172cf9`；相同 query 的 adapter 尝试由 2 次降至 1 次，两个 typed search 的参数/顺序不变。对照日志 `1999wiki-d-shared-dense-parity-daa1be29520940f2ac41d3e50b500ac4/probe.log`，SHA `da6142111d501e8511f99f102d1aa2c6e74a636f7f32c0ccad7985468284f504`。失败分类、不同 query/当前向量身份、并发 KB/跨请求隔离均通过；SDK HTTP 与其他调用/扫描门仍未闭合，11 项本地 producer/45 项待完成和 `no_go` 不变。E 树/index 干净，未合并 main，冻结四输入、Spec、observations 和 eval 测试字节未变，无真实构建或外部操作。

**接续只核定最小调用观测接线：** 同一 E 在 `d35a4d1` 仅核对现有 RequestTrace 如何覆盖 request-level detector 的普通入口和 continuation 再验证，以及 reranker 实际 `urlopen` 边界；区分一次执行的完整覆盖与“没有 span 所以是零”。沿用此前六门分母盘点，不重开全量审查，不新增矩阵/文档/receipt，不改代码或运行测试/采集。给 D 一条紧凑的接口与缺口报告：准确调用者/参数、实际可复用的完成事件、失败或绕过入口、当前 collector 未覆盖的场景，及同一批 producer 能否成立。不得预先扩大到 HTTP 通用埋点、SDK 重试、AnswerScope 或标签构造；D 同步核对后放行最小连贯批。

**2026-09-09：用户批准五条状态场景与协议拒绝口径的窄修。** 上述只读核对已结束：`auth-08/09/10/11`、`answer-scope-07` 缺完整前序输入；旧 capture 按普通文字执行它们，不能作为真实续页/锚点场景基线。`authorize_story_anchor_follow_up` 也没有生产调用者，原测试直接调用 helper→Retriever，不能证明第二轮正常问答可达。按以下顺序在同一 E/D 内串行闭合，不因修复新增泛化框架或监督回执：

1. **先接通已批准的 anchor 产品入口。** E 从 `d35a4d1` 修改范围仅 `src/rag/{chain,execution,route_policy,story_authorization}.py` 和现有 `tests/{test_story_segment_runtime,test_story_authorization,test_conversation_memory,test_request_plan}.py`（只需实际相关文件）。复用原 Finalizer、固定 `StoryFollowUpResolver`、`project_story_anchor` 和 `authorize_story_anchor_follow_up`，把合法 follow-up 接入统一授权 envelope；不能增加独立检索路线、从期望 Owner/Planner rewrite 创建锚点、跳过 envelope 重验或重复调用 Detector/Planner。显式 Story、冲突角色/Topic/Story、多 Story-required 子任务及无回指问题保持原拒绝/授权边界；未持有合格已提交 anchor 时确定性拒绝，local 与 open-domain 不因此升级。
2. **同请求使用同一真实 projection 与 UTC 授权时刻。** clock 可注入，运行时默认当前 aware UTC；授权、执行前 envelope 重验、续页 action builder 的 envelope 核对必须使用同一请求的输入，不能把已验收 anchor 再按空会话/direct-only 路线重算。复用现有内部参数/结果传递，不新增公开 schema、可变 anchor sidecar 或授权签名层。缺失可信上下文不能接受外来 anchor envelope；expiry/clear/identity mismatch、伪造 context 仍严格拒绝。第一轮与后续轮的 set/clear 仍由原 `build_completed_turn` 与 lease commit 负责。
3. **入口级测试，不以 helper 成功替代。** 在已安装小来源链上，外部 Planner/生成/向量边界可用确定替身；实际执行第一轮显式单 Story→真实结果与引用校验→原子提交→第二轮 `chain.execute/prepare_execution`。证明合法 anchor 被消费、授权 Owner/来源正确、Detector 每请求一次、无额外 Planner；覆盖两 Story 清除后不复活、到期/身份不匹配/无 anchor、实体冲突和独立新问题拒绝，以及 REST/SSE 共用 prepare 后的语义。可复用现有非 UI 会话测试，无需启动服务器。先产生能揭示未接线的 RED，再最小实现，运行四个相关测试文件及原 Story runtime/authorization/会话邻接；D 独立验收后提交，E 不自行提交。不顺手补调用 scorer/trace 或修 Planner 语义。D 另准许 `tests/test_route_policy.py` 中唯一精确签名断言同步增加 `conversation_projection/utc_now`，并断言两者为 keyword-only；只反映第 2 项已批准接线，不伪装旧签名或扩大产品参数。
4. **D 冻结明确的 v2 执行场景，再交 E 统一消费。** 旧四份 v1 gold/threshold/baseline/equivalence 字节保留历史身份，不覆盖、不自动转换旧观测。新场景显式区分前序真实请求、目标业务请求与协议拒绝；续页只选择前序实际返回 action，锚点只使用真实成功并已提交的 turn。五例的独立场景输入由 D 明确编写，不能运行时从 expected Owner/gold 反填授权。未修改的 80 例保持原题干、gold/预期；五例的改动与历史基线不可比范围明示。协议解析拒绝在业务 Detector 门中记为不适用、单独严格核对拒绝且 Planner/检索/生成均未进入，不补零冒充缺测、不降低原数值质量/性能阈值。此次批准允许修正这五例与对应适用口径；不批准重写其他标签或伪造新 baseline。
5. v2 输入与唯一 collector/validator/评分消费者在后一批贯通；采用有限的现有 direct/continuation/anchor 输入类型，不做场景 DSL 或另一个 RAG runner。前置失败、真实动作缺失、target 与 seed 关系不符都必须保留为未完成/失败，不能借用手工 receipt 补齐。新旧场景的匹配、计时与必要基线采集边界由 D 在输入冻结时明示。此阶段起初仅放行第 1–3 项产品修复与 D 编写第 4 项输入；它们现已完成，第 5 项只按下方消费者批的明确范围执行。

Conda `1999wiki`、OS temp、同一 E `gpt-6-astra / xhigh / 普通速度` 与两层拓扑不变。无真实全量构建、LLM/embedding/Milvus/SSH/媒体/生产写入，不合并 main、不激活；最终真实构建仍仅由 D 在完整 E 验收合并后执行。

**2026-09-09 v2 场景输入冻结（仅输入，不代表执行通过）：** `eval/story_segment_eval.v2.jsonl` 使用 `rag.story-segment-eval-case/v2`，SHA-256 `20499bcbac896b6ff5ba14c65db657a7fe0669b6d5db5136365f0845371a6160`。D 按上述用户批准范围复核：85 个唯一、有序用例，80 个普通用例除版本和新增 `execution` 外逐字段不变；全部 95 组 Atom gold、Topic 来源、source relevance、Owner 标签、来源哈希与原 review 保留。原 review 仅指原事实证据审核，不表示用户逐句审核了新增前序请求。此前顶部暂停中的 v2 草稿身份只作历史记录，由本节替代。

| 用例 | 独立编写的真实前序与目标 | 变化的含义 |
|---|---|---|
| `auth-08` | 前序与目标均为“请依次介绍《第二章2-12》、《第二章2-13》、《第二章2-14.1》、《第二章2-11.2》。”；消费前序实际返回、`target_subtask_order=1`、`page_index=1` 的 continuation。 | `page_index` 是零起点；第二页应覆盖原 gold `story:100220`，不是第三页，也不是把按钮文字作为原问题。 |
| `auth-09` | 同上取得真实 action 后，仅把其 `canonical_payload_body_sha256` 首个十六进制字符确定性改为不同字符，不重算哈希或改写其它字段。 | 明确 `protocol_rejected`；没有业务 ResponsePacket，预期 authorization origin/outcome 为 null。预期零调用必须由目标拒绝边界实测，不是缺 trace 补零；不将本地解析异常冒充已观测 HTTP 422。 |
| `auth-10` | 前序“请介绍剧情《第二章2-12》的开头。”成功引用并提交 set；目标仍为“后来发生了什么？”。 | 实际消费已提交 `story:100221` anchor，保留原目标 gold。 |
| `auth-11` | 先“请介绍剧情《第二章2-11.2》的开头。”提交 set，再“请比较剧情《第二章2-12》和《第二章2-13》中的事件。”提交 clear；目标改为“后来发生了什么？”。 | 必须先有 anchor 再因多个 Story 清除；相同的合法回指不得复活旧 anchor。目标保持现有 Policy 的 `direct_query` 拒绝，不为标签修改产品拒绝来源。 |
| `answer-scope-07` | 前序“请介绍剧情《第四章4-11.1》的开头。”成功引用并提交 set；目标仍为“接着呢？”。 | 实际消费 `story:100414` anchor，保留原 AnswerScope 与 gold。 |

- **有限输入协议：** 普通用例只有 `execution={entry:direct}`；其它只使用 `entry=continuation|anchor` 和显式 `setup_queries`。anchor 的 `setup_expected_events` 一项对应一个真实提交；它和 `anchor.owner_id`、gold、预期 Owner 都只用于核对结果，不能构造授权、projection、action 或模型回复。来源 Atom 文件 SHA `40d17b412a60c44bcdab953d9d382d3fb32f0812026b0eb51b972961c40999a1` 已重验，五个前序标题与来源中的自然名称一致。
- **真实入口与隔离：** 每个 warmup/计时重复使用新的会话，先实际执行前序，再执行目标；anchor 前序须通过原引用校验与 lease commit，不能重放手填 CompletedTurn。continuation 前序可以是合法的 needs-continuation 边界响应，只要求真实有效 action，不要求先命中 gold 或制造非空 turn；lease 仍正常释放。续页只按实际 action 中的 final plan/subtask order 与 page index 唯一选择；动作缺失/歧义、前序失败或事件不符均为场景失败，不能使用 expected Owner 搜索替代 action。`auth-11` 的 clear 是最后一次前序提交，目标则验证无复活。普通用例不受这些准备步骤影响。
- **计量边界：** 前序调用和耗时与目标分别记录；目标 gate 的分母只包含目标执行，但不能隐藏准备成本。协议拒绝只接受实际入口的已定义解析拒绝，不接受任意异常；证明尚未进入 Planner/Detector/检索/生成后才可记录对应零次。它不属于业务 Detector 每请求一次门的适用分母，不能伪造 `not_applicable` 业务响应。NullTrace、采集缺失、前序失败均不等于实测零次或通过。
- **历史基线与最终门禁：** 四份 v1 输入保留原字节。五条状态场景的旧无状态观测不可比较，不重写旧 baseline、不用候选自身或手工零值补对照。80 条普通用例只有在题干、全部语义字段及来源身份逐项相同后才允许明确关联旧观测，不能因 query_id 相同就跨版本自动转换。候选绝对质量仍覆盖全部 95 组 gold；需要完整对照而暂缺五条有效对照的指标保持未测，待 D 在真实评测阶段提供相应控制运行，不能缩小分母或降低阈值来通过。
- **交接边界：** 输入提交仅冻结独立场景及口径，不证明新 collector/validator/scorer 可用或新场景已通过。输入冻结时 E 仍只执行 anchor 批第 1–3 项；D 现已验收该批并把固定输入交接至 E，第 5 项按下方统一消费者范围执行，不读取 D 的未提交草稿，不建立第二个 runner/场景 DSL/监督回执。

**2026-09-09 第 5 项消费者批（D 已放行，单一串行批）：** 起点为 E `f10a63c` 干净树。只在既有 `src/rag_eval/{story_segment_baseline,story_run_observations}.py`、`src/rag/{execution,story_authorization}.py`、`scripts/{evaluate_story_segment_rag,capture_story_segment_baseline}.py` 和 `tests/{test_story_segment_baseline,test_story_segment_eval,test_story_segment_runtime}.py` 实施；`story_authorization` 仅允许下述精确解析异常。输入、thresholds、旧 baseline/equivalence、业务规划/授权算法、runner、tracing 框架及其它文件不改。真实五状态对照的取得留给 D 后续评测决定，本批不伪造、不替换成候选自身，也不为缺控制阻断合法候选观测的保存。

- loader 严格区分 v1 历史输入与 v2 场景，不能混装。保留 v1 规则；v2 以唯一 query_id 和整份固定输入身份识别场景，允许 auth08/09、auth10/11 同题干但不同前序/动作。校验有限 execution 字段与 cross-links，null outcome 只允许明确协议拒绝。新 collect 只接受 v2；旧 capture 显式拒绝 v2，不能因共享 loader 升级再次默默生成无状态 baseline。
- 沿原 `collect_story_run` 与实际 `_execute_once` 执行新隔离会话的 setup→真实提交/释放→目标。复用已有 `build_completed_turn`、lease、projection 及可注入 clock；只捕获实际 UTC，不在完成后猜测授权时刻。按冻结场景选择实际公开 action、做唯一 hash 字符变更。保留预期与观测的区别：Owner/gold 只用于核对，不造状态；有效但错误的业务答案不能因不符合 gold 被改写成协议错误。
- 单一 observations 升为 `rag.story-run-observations/v3`，performance 形状变更同步升为 `rag.story-run-performance/v2`；原未发布观测保留历史字节但不自动迁移。有限状态为 `completed/protocol_rejected/setup_failed/unsupported_control`；异常的业务 ResponsePacket 仍按原字段表达，意外目标异常继续失败，不能套用 protocol_rejected。无真实 prepared/response、未运行的 target、无有效 trace 时相应值为 null。保留每个 lane/case/repeat 的记录，不静默丢掉失败或不支持的格子。
- setup 复用同一既有执行投影，记录实际提交结果及原 ConversationTurn 所需身份/事件；target 通过有序已提交 turn 身份关联，不再复制一套完整 conversation projection/envelope/ledger 作为第二事实源。现有 dataclass/校验器可复用，不新建通用序列化框架。验证前序、提交、所选 action、target、来源 context 与固定 runtime 的闭包；只在需要原始输入的边界校验，进程内不反复重建同一 projection。继续保留已有 ranks/context/source-map/引用验证。
- 协议拒绝的最小运行时接点：在现有 continuation decoder 的 body-hash mismatch 分支使用一个窄 `ValueError` 子类，保留拒绝条件与原消息，不建立通用错误码框架；execution 在原 decoder 调用上用现有 RequestTrace span，自动保留错误类型。采集只接受该精确类型及真实终止 span，不比较异常字符串，也不重复在 collector 计算产品 hash 来判断拒绝。其它异常、丢失 span、NullTrace 均不能宣称四类下游调用为零；不改通用 HTTP/SDK/reranker 埋点，不声称未实现的调用门通过。
- active v1 的五个非 direct 场景依据实际已安装能力记为 `unsupported_control`，setup/target 均未运行、计量为 null；candidate 安装缺失仍是错误，不能借此分类跳过。仅 80 个逐字段/来源一致的 direct 例可关联旧控制：先完整验证旧 receipt/equivalence 及其 pin 的 v1 输入，再进行关联。evaluate CLI 仅新增旧输入路径，其预期 SHA 从已验证 receipt 取得，避免第二个自报身份。旧五例不借 query_id、baseline=0 或改写哈希强行兼容。
- 现有 scoring/diagnostics/performance 同步消费状态与 setup/target 分离成本；候选绝对质量继续覆盖全部 95 组。缺少三组有 gold 状态例的有效控制时，final_evidence_recall 的 not_below 比较仍未测；其它受影响比较同理，不缩到 80 条冒充完整通过。绝对数值可作诊断，缺比较观测不送入现有 gate；有效且不含五例的 middle/late 对照可保留。协议不适用与真实缺测分开，不给缺失 response 补空对象/零分。TTFT/HTTP 等原待测项不因内部计时可用而转为通过。
- 先用已有安装 fixture/CLI 节点的 RED 暴露重复题干拒绝、空历史执行、动作未消费、protocol null 崩溃、旧 baseline hash 不匹配，再实现唯一消费者并 GREEN。覆盖真实 set→consume、set→clear→拒绝、真实 action→目标页、唯一 tamper→精确拒绝、setup 失败/动作歧义、跨 case/repeat 隔离、伪造提交/trace/动作拒绝和 baseline 80 匹配/五例不可比。完整运行三个允许测试文件及必要原 API/continuation/anchor 邻接；D 独立复验后一次检查点提交。只用 Conda `1999wiki`、小 fixture、OS temp；不做真实85题采集或其它外部操作，不新增子任务、模块、测试框架、矩阵或回执。E 不 stage/commit，不自动进入其余45门或真实构建。

- 普通等价重构先运行现有特征测试，再修改，再运行定向/相邻回归；修复缺陷时增加能暴露根因的测试。D 在批次完成后独立审查，不为每个辅助函数或每次恢复新增 RED acceptance、ledger 或 receipt。
- 验证输入和跨进程/外部请求时保留严格检查；进程内使用已验证的不可变值，避免反复序列化和重验同一事实。跨请求 continuation 和外部文件不能按进程内可信对象处理。
- 最终离线业务产物仍须证明确定性，并绑定已提交代码；日常等价重构不触发全量快照构建。代码身份变化不要求撤销已完成历史任务或重新运行 C/D0。
- 旧 D2 v1、旧日志与失败构建保持原字节，作为历史证据。S2/S3 接口确定后统一生成与消费者一致的继任交接契约；不在每次修复时增加一层证据，也不伪造旧哈希来兼容新规则。
- D 在 main 维护本节，E 在原工作树完成代码；只放行当前批次。D 审查前 E 不提交、不合并、不启动下一批次或真实全量构建。
- 不要求固定净删行比例；验收重点是减少重复事实源、分支和依赖，且保持行为。只有外部权限扩展、破坏性操作、产品/质量/安全边界改变或客观无法继续时升级给用户。

---

**Goal:** 在线程 E 启动前冻结可观察监督、评测集、阈值和可信 baseline；在线程 E 交付后由 D 独立审查、合并、执行一次 Typed Dense 影子向量构建和完整 go/no-go 评测，同时保持生产激活为独立门禁。

**Architecture:** 本计划只负责两端。线程 C 先完成 C8b、C8c、C8d、C9；D 独立验收并把 C 合并到 `main`，运行合并后真实 fidelity，生成机器可验证的 C release receipt。只有该 receipt 通过后，D0 才能在同一 `main` 中升级 Codex 监督器、冻结 Story gold/baseline/阈值并创建 E worktree；E0–E5 由独立的线程 E Plan 串行实现。E 交付后，D 校验每个 Task 的独立提交和不可变 handoff，合并至 `main`，再由 D 独占 embedding API 与 Milvus 写权限，创建全新的 typed shadow collection、运行真实评测并生成逐项 go/no-go receipt。通过评测不等于激活。

**Tech Stack:** Conda `1999wiki` 中的 Python 3.11.15（`D:\Anaconda32024\envs\1999wiki\python.exe`，`sys.prefix=D:\Anaconda32024\envs\1999wiki`）、pytest 9.1.1、Codex CLI、PowerShell 5.1、Git worktree、JSON/JSONL、SHA-256、Milvus、现有 embedding API、现有 Huiji corpus/provenance/evaluation contracts。

## Global Constraints

- 批准的设计源头：`docs/superpowers/specs/2026-07-30-rag-story-segment-retrieval-design.md`。
- 批准基线提交：`300e4066630c6564d56157442765a4675b783590`。
- 批准 Spec SHA-256：`61bf46e1ec6f44b330913d1b1effdfd1828edf72b13ccd7ea8f60c61fa7f405d`。
- 配套线程 E Plan：`docs/superpowers/plans/2026-07-30-rag-story-segment-e-implementation.md`。
- 执行顺序严格为 `C8b → C8c → C8d → C9 → D review/merge C → D post-merge C fidelity → D0 → E0 → E1 → E2 → E3 → E4 → E5 → D merge E → D post-merge candidate rebuild → D shadow embedding → D go/no-go`。
- D 在 `D:\1999Wiki` 的 `main` 工作树执行；E 使用 `codex/rag-e-story-segment` 和 `D:\1999Wiki.worktrees\rag-e-story-segment`。
- E 固定使用 `gpt-5.6-sol`、标准速度、`workspace-write`、`fast_mode=false`、`multi_agent=false`，禁止子代理和第二个 CLI worker。
- 所有 Python 和 pytest 命令使用绝对解释器 `D:\Anaconda32024\envs\1999wiki\python.exe`；禁止裸 `python`、`py` 或裸 `pytest`。
- C release receipt 未通过前不得执行任何 D0 Task 或创建 E。E Plan 未经 D 和用户审核前不得实施。
- 线程 C 的 C8b/C8c/C8d/C9 代码、决策、测试和自包含真实 fidelity 证据必须先由 D 验收并进入固定 `main` 提交；未跟踪文件、C worktree、聊天摘要和临时诊断目录均不能成为 E 输入。
- E 只能消费 C 合并后由 `main` 重建并在 C release receipt 中固定的公共 Parent、Story Atom、source refs、migration/fidelity 和 runtime artifact；不得直接引用 C 分支、C worktree 或 ignored 诊断目录。
- E 不得调用 embedding API，不得创建或写入 Milvus collection，不得下载媒体，不得修改 active pointer，不得激活候选。
- 只有 D 可调用 embedding API 和创建 Typed Dense shadow collection；D 也不得覆盖、复用或删除 active collection。
- Reranker 全程关闭，API 调用次数必须为零；不得以开启 reranker 掩盖 Segment Dense 或融合指标不足。
- P0 质量标记只生成反事实报告，不参与真实排序、过滤或 go/no-go 分数。
- Story Atom 保留 BM25，Story Atom 不进入新 Dense 输入；非 Story Child 继续进入 Dense 输入；Story Segment 是唯一 Story Dense 单元。
- D 不修改或提交用户已有的以下工作区内容：
  - `docs/huiji-crawler/plans/README.md`
  - `docs/huiji-crawler/specs/2026-07-20-windows-crawler-p2-credential-lifecycle-design.md`
  - `docs/huiji-crawler/plans/2026-07-29-windows-crawler-p2-credential-lifecycle.md`
  - `docs/superpowers/plans/2026-07-24-blue-green-final-hardening.md`
  - `docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md`
  - `docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md`
- 每个代码任务采用 TDD：先运行最小 RED 并确认预期失败，再做最小实现，再运行定向和相邻回归。
- 每个提交前运行 `git diff --check`、阶段测试和 `git status --short`，只暂存任务列出的文件。
- 若 E worktree 的共享 Git 元数据权限阻止提交，E 停止并报告；D 可在主监督上下文精确暂存已批准文件，但不能代替测试或扩展范围。

---

## 1. 双 Plan 职责与交接

### 1.1 D 独占职责

```text
C 发布门
├─ 验收 C8b、C8c、C8d、C9 独立提交
├─ 合并 C 到 main
├─ 运行合并后真实 fidelity 与保护状态检查
└─ 生成 C release receipt

D0
├─ 扩展监督器支持 E
├─ 冻结 gold、threshold、active baseline 与 Atom 等价 receipt
├─ 绑定 C release receipt
└─ 创建并启动受监督 E worktree

E0–E5 期间
├─ 审查阶段 diff、测试、真实快照证据
├─ 接受或退回 Task 提交
└─ 不替代 E 实现

E 交付后
├─ 合并 main
├─ 固定 Typed Dense JSONL 与模型身份
├─ 调用 embedding API
├─ 创建全新 shadow collection
├─ 运行真实 Dense/端到端评测
└─ 生成 go/no-go；不自动激活
```

### 1.2 E 独占职责

```text
E0  Story structure sidecar
E1  Segment、Context Unit 与 Atom citation spans
E2  Typed Dense 离线输入、schema、假向量适配器
E3  RequestPlan v2、Story 授权、融合与预算
E4  Runtime、公开契约、AnswerScope 与记忆
E5  离线评测、容量报告和不可变 D handoff
```

E 不得把“D 后续会重建向量”当成缺少 typed schema、builder、反序列化、fake-vector 测试或 provenance 的理由。D 不得在合并后临时补写 E 应交付的业务契约。

### 1.3 Handoff 唯一契约

E5 必须先用 `[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')` 生成 `$RunId`，再在 ignored 的新目录 `eval/story_segment/handoffs/$RunId/` 写出：

```text
story_segment_e_handoff.v1.json
story_segment_e_handoff.v1.sha256
typed_dense_units.v1.jsonl.sha256
artifact_manifest.v1.json
candidate-build-input.v1.json
candidate-build-input.v1.sha256
deployment-inventory.v1.json
offline-capacity-estimate.v1.json
offline_gate_report.v1.json
protected_state_pre.v1.json
protected_state_post.v1.json
test_receipt.v1.json
```

`story_segment_e_handoff.v1.json` 的必需字段：

```json
{
  "schema_version": "rag.story-segment-e-handoff/v1",
  "spec_commit": "40-hex",
  "spec_sha256": "64-hex",
  "d0_commit": "40-hex",
  "e_commit": "40-hex",
  "source_snapshot_identity": {},
  "artifact_paths": {},
  "artifact_sha256": {},
  "schema_sha256": {},
  "ordered_row_hashes": {},
  "row_counts": {},
  "embedding_input_identity": {},
  "candidate_build_input": {"path": "", "sha256": "64-hex"},
  "deployment_inventory": {"path": "", "sha256": "64-hex"},
  "offline_capacity_estimate": {"path": "", "sha256": "64-hex"},
  "retrieval_config_identity": {},
  "story_fusion_config_identity": {},
  "offline_gate_report_sha256": "64-hex",
  "protected_state_pre_sha256": "64-hex",
  "protected_state_post_sha256": "64-hex",
  "protected_drift_count": 0,
  "task_receipt_sha256": {},
  "reranker_call_count": 0,
  "forbidden_operation_counts": {},
  "remaining_blockers": [],
  "ready_for_d_shadow_build": false
}
```

`ready_for_d_shadow_build=true` 只能表示 E 的离线门通过，不代表生产激活获批。

---

## 2. 文件职责

### 2.1 D0 新建

| 文件 | 单一职责 |
|---|---|
| `src/rag_eval/story_segment_baseline.py` | 冻结 gold schema、baseline 等价 Atom 匹配、逐项 receipt 和 baseline 汇总 |
| `scripts/capture_story_segment_baseline.py` | 只读捕获当前 active retrieval/final-context baseline，不调用生成答案作为证据 |
| `tests/test_story_segment_baseline.py` | 等价匹配、歧义、单次 span 消费、stage 隔离和确定性测试 |
| `eval/story_segment_eval.v1.jsonl` | 提交的 Story gold 查询与 required Atom/group、授权和答案范围预期 |
| `eval/story_segment_thresholds.v1.json` | 第 26.1 节全部硬阈值及 metric direction |
| `eval/story_baseline_atom_equivalence.v1.jsonl` | 当前活动系统逐 query/result/Atom 的确定性匹配 receipt |
| `eval/story_segment_baseline_receipt.v1.json` | baseline 输入、代码、活动 snapshot、输出哈希和指标 |
| `src/codex_supervisor/task_receipts.py` | allowlist tree identity、task receipt 与 D RED acceptance 的 canonical contract |
| `scripts/codex-supervisor/Write-TaskReceipt.ps1` | 在 E/D 两侧调用同一 receipt contract，不自行重算身份 |
| `tests/test_codex_supervisor_task_receipts.py` | tracked/untracked/absent tree、RED witness 和 log hash 防漂移 |

### 2.2 D0 修改

| 文件 | 修改职责 |
|---|---|
| `.gitignore` | 只为四个版本化 Story eval/baseline 文件添加精确 negation；其余 `eval/*` 继续 ignored |
| `config/codex-supervisor.workers.json` | 升级 `codex-supervisor/v2` 并新增独立 E branch/worktree |
| `src/codex_supervisor/contracts.py` | 唯一 `SUPPORTED_WORKERS=("A","B","C","E")`、v2 配置和 worker validation |
| `src/codex_supervisor/cli.py` | 机器可读 `worker-list/worker-validate`，所有 CLI choices 使用公共集合 |
| `src/codex_supervisor/processes.py` | E 进程身份和兼容读取 |
| `src/codex_supervisor/runner.py` | E runner/request validation 和现有 A/B/C 恢复兼容 |
| `scripts/codex-supervisor/Start-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Resume-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Stop-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Watch-Worker.ps1` | 通过公共 worker validation 接受 E |
| `scripts/codex-supervisor/Open-SupervisorWindows.ps1` | 从公共 worker list 打开 A/B/C/E 观察器 |
| `scripts/codex-supervisor/Show-Dashboard.ps1` | 维持公共 dashboard 入口 |
| `tests/test_codex_supervisor_contracts.py` | v2、A/B/C 状态兼容和 E 隔离 |
| `tests/test_codex_supervisor_cli.py` | worker-list/validate 和 E 命令 |
| `tests/test_codex_supervisor_processes.py` | E 精确进程身份 |
| `tests/test_codex_supervisor_powershell.py` | 脚本无手写 worker 集合 |
| `tests/test_codex_supervisor_e2e.py` | E 启动、关闭观察窗口、恢复和日志隔离 |

### 2.3 D 后置只读或外部写入口

线程 E 必须交付、D 只负责执行：

| 文件 | D 使用方式 |
|---|---|
| `scripts/probe_story_segment_storage.py` | 从 deployment inventory 只读探测真实云端 Milvus/artifact/staging 卷并生成容量 receipt |
| `scripts/build_huiji_typed_index.py` | 先做只读 Milvus preflight，再读取 candidate-build-input、调用 embedding 并 create-new shadow collection |
| `scripts/evaluate_story_segment_rag.py` | 先生成同提交性能 control receipt，再对指定 shadow collection 运行冻结 gold、baseline/candidate 和 go/no-go |
| `src/rag/vectorstore.py` | 使用 E 已验收的 typed schema/序列化/反序列化实现 |
| `src/rag_eval/story_segment_runner.py` | 生成逐项 numerator/denominator/baseline/candidate/delta/threshold 报告 |

D 不在后置阶段改写这些文件；若真实执行暴露产品缺陷，停止、记录新 correction gate，并退回 E 或另立受审修复，不在生产命令中打补丁。

---

## 3. C 发布依赖硬门（D0 前置）

### Task DC0：完成、验收并合并 C8b–C9

**Purpose:** 线程 E 的 Segment、引用与 baseline 必须建立在 C 已发布的 Story Atom 上。本门证明 C 的最终代码、语料契约和真实快照 fidelity 已进入 `main`；“文档存在”或“C 工作树能运行”均不算发布完成。

**Inputs:**

- `docs/superpowers/plans/2026-07-29-rag-thread-c-closure-gates.md`
- `docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md`
- C8a checkpoint `012c7ca6b3abaa0445ccd00a8974ea4fefcbd333`
- 后续 C8b、C8c、C8d 独立实现提交
- C9 D-reviewed checkpoint commit 与随后生成的 merge-ready handoff

**D-owned ignored output:**

```text
eval/story_segment/dependencies/<run-id>/c-release-receipt.v1.json
eval/story_segment/dependencies/<run-id>/c-release-receipt.v1.sha256
eval/story_segment/dependencies/<run-id>/c9-intake-receipt.v1.json
eval/story_segment/dependencies/<run-id>/c9-intake-receipt.v1.sha256
eval/story_segment/dependencies/<run-id>/protected-state-diff.v1.json
eval/story_segment/dependencies/<run-id>/post-merge-fidelity.v1.json
```

- [ ] **Step 1: 验收 C8b、C8c、C8d、C9**

逐阶段验证：

```text
C8b  user-approved Story/legacy Parent-Child migration decision + implementation commit
C8c  user/D-approved legacy media classification decision + implementation commit
C8d  self-contained read-only fidelity entry point commit；入口固定为 scripts/diagnose_huiji_corpus_fidelity.py
C9   full regression + deterministic fixture closure + ownership audit；
     D 验收后创建 checkpoint commit，再从该 commit 生成 handoff
```

每个阶段必须有 D 批准的 commit SHA、文件 allowlist、RED/GREEN 命令与结果、真实快照或明确 `not_applicable` receipt。C9 正常没有 tracked 产品 diff，因此在 D 验收完整回归和 scope audit 后，必须从已验收 C8d HEAD 创建显式 checkpoint：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $C8dAcceptancePath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedC8dAcceptanceSha256
)

$ObservedC8dAcceptanceSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $C8dAcceptancePath).Hash.ToLowerInvariant()
if ($ObservedC8dAcceptanceSha -ne $ExpectedC8dAcceptanceSha256.ToLowerInvariant()) {
  throw 'C8d acceptance hash mismatch'
}
$C8dAcceptance = Get-Content -Raw -LiteralPath $C8dAcceptancePath | ConvertFrom-Json
if ($C8dAcceptance.schema_version -ne 'rag.thread-c-phase-acceptance/v1' -or $C8dAcceptance.phase -ne 'C8d') {
  throw 'Unexpected C8d acceptance'
}
$ExpectedC8dCommit = [string]$C8dAcceptance.commit
if ((git rev-parse HEAD) -ne $ExpectedC8dCommit) { throw 'C9 did not start from accepted C8d' }
if ((git status --short --untracked-files=no)) { throw 'C9 tracked tree is not clean' }
git commit --allow-empty -m "chore(rag): certify thread C regression handoff"
if ($LASTEXITCODE -ne 0) { throw 'C9 checkpoint commit failed' }
$C9Commit = (git rev-parse HEAD).Trim()
$C9Parent = (git rev-parse HEAD^).Trim()
if ($C9Parent -ne $ExpectedC8dCommit) { throw 'C9 parent is not accepted C8d' }
if ((git diff-tree --no-commit-id --name-only -r HEAD)) { throw 'C9 checkpoint unexpectedly changes tracked files' }
```

只有该 checkpoint 成功后才能生成 handoff；handoff 的 `c9_commit` 必须等于 `$C9Commit`，并固定 D 已验收的测试/fixture/protected receipts。不得先生成 handoff 再补写 commit SHA。C8c 若对缺少本地媒体字节保持 blocker，可以作为明确未解决项留在 C receipt；但只要该 blocker 会影响 E 所需的 Story Atom、Parent、source refs 或文本 fidelity，就不得放行 E。

- [ ] **Step 2: 审查 C 分支并固化 C9 intake**

D 重算 C9 handoff、所有 artifact 和测试 receipt 的 SHA-256；确认 C 分支不包含 raw snapshot、ignored run output、pytest 临时目录、supervisor state、向量、下载媒体或生产指针修改。随后把 C9 handoff 复制到本次 D-owned create-new dependency root，并写 `rag.thread-c9-intake/v1` receipt。Receipt 至少固定：

```text
c8b/c8c/c8d/c9 commit SHA
C9 handoff copied relative path / size / SHA-256
C8d entrypoint relative path / SHA-256 / schema version
source snapshot / active baseline / protected manifest relative paths and SHA-256
expected C8d output names
```

后续 C8d 命令只能从该 receipt 解析输入；不得再读取 C worktree、C supervisor state 或旧 ignored run 目录。

- [ ] **Step 3: 合并 C 到 main**

保存并保护当前用户工作区边界；非破坏性合并 C。只解决 C 已批准提交与 `main` 的真实冲突，不 stash/reset/checkout/delete 用户文件。

- [ ] **Step 4: 在合并后的 main 运行固定 C8d CLI**

C8d 必须提交且 C9 handoff 必须固定：

```text
entrypoint.relative_path == scripts/diagnose_huiji_corpus_fidelity.py
entrypoint.sha256
entrypoint.schema_version == huiji.corpus-fidelity-diagnostic/v1
source snapshot / active baseline / protected manifest paths and SHA-256
expected output file names
```

D 先验证入口来自合并后的 commit、SHA 匹配且不能 `exec()` 或 import 旧 ignored run 脚本，再运行：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $C9IntakeReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedC9IntakeReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$Project = 'D:\1999Wiki'
$C9IntakeReceiptPath = [IO.Path]::GetFullPath($C9IntakeReceiptPath)
$ObservedC9IntakeSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $C9IntakeReceiptPath).Hash.ToLowerInvariant()
if ($ObservedC9IntakeSha -ne $ExpectedC9IntakeReceiptSha256.ToLowerInvariant()) {
  throw 'C9 intake receipt hash mismatch'
}
$C9Intake = Get-Content -Raw -LiteralPath $C9IntakeReceiptPath | ConvertFrom-Json
if ($C9Intake.schema_version -ne 'rag.thread-c9-intake/v1') {
  throw 'Unexpected C9 intake schema'
}
$C8dEntrypoint = [IO.Path]::GetFullPath(
  (Join-Path $Project ([string]$C9Intake.c8d_entrypoint.relative_path))
)
if ([string]$C9Intake.c8d_entrypoint.relative_path -ne 'scripts/diagnose_huiji_corpus_fidelity.py') {
  throw 'Unexpected C8d entrypoint path'
}
$ObservedEntrypointSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $C8dEntrypoint).Hash.ToLowerInvariant()
if ($ObservedEntrypointSha -ne [string]$C9Intake.c8d_entrypoint.sha256) {
  throw 'C8d entrypoint hash mismatch'
}
$C8dRunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$C8dRunRoot = Join-Path $Project "eval\story_segment\dependencies\$C8dRunId\c8d"
$C8dLog = Join-Path $C8dRunRoot 'c8d-cli.log'
$null = New-Item -ItemType Directory -Path $C8dRunRoot
$C8dArgs = @(
  $C8dEntrypoint,
  '--project-root', $Project,
  '--c9-intake', $C9IntakeReceiptPath,
  '--expected-c9-intake-sha256', $ExpectedC9IntakeReceiptSha256,
  '--output-root', $C8dRunRoot,
  '--read-only'
)
& $Python @C8dArgs 2>&1 | Tee-Object -LiteralPath $C8dLog
if ($LASTEXITCODE -ne 0) { throw "C8d post-merge fidelity failed: $LASTEXITCODE" }
```

调用者必须显式传入已验收的 `C9IntakeReceiptPath` 和期望 SHA-256；wrapper 与 C8d CLI 都先验哈希再解析。C8d 自身从 intake 解析并逐项验证 C9 handoff、source snapshot、active baseline、protected manifest 和 expected outputs，不接受这些对象的重复 CLI 参数；若 wrapper 所见 entrypoint 与 C8d 所见 intake 身份不一致则停止。运行完整恢复快照后要求：

```text
diagnostic status == completed
FidelityResult returned normally and its exact payload SHA-256 is recorded
every FidelityResult blocker is classified exactly once as story_dependency or non_story_media
story_dependency_blockers == []
Story Parent/Atom/source-ref closure == true
all candidate Story records have an approved fidelity class
protected identity count == 32
protected drift count == 0
network/download/embedding/vector/activation/pointer/production write count == 0
```

若仍有媒体证据 blocker，`FidelityResult.passed` 可以为 false，但这些 blocker 必须逐项进入 `non_story_media_blockers`，不得猜测核销，并证明不改变 E 所需的 Story 文本/Atom 输入；分类并集必须与原始 blocker 多重集合完全一致且交集为空。任何 Story 文本、Atom、source-ref 或 migration blocker 立即停止。

- [ ] **Step 5: 生成 C release receipt**

Receipt 至少包含：

```json
{
  "schema_version": "rag.thread-c-release/v1",
  "c_phase_commits": {
    "c8a": "40-hex",
    "c8b": "40-hex",
    "c8c": "40-hex",
    "c8d": "40-hex",
    "c9": "40-hex",
    "c9_handoff_sha256": "64-hex"
  },
  "approved_decisions": {
    "c8b_story_migration_sha256": "64-hex",
    "c8c_legacy_media_sha256": "64-hex"
  },
  "c_merge_commit": "40-hex",
  "c8d_execution": {
    "command_schema_version": "rag.c8d-post-merge-command/v1",
    "entrypoint_relative_path": "scripts/diagnose_huiji_corpus_fidelity.py",
    "entrypoint_sha256": "64-hex",
    "c9_intake_receipt_sha256": "64-hex",
    "c9_handoff_sha256": "64-hex",
    "argv": [],
    "exit_code": 0,
    "log_sha256": "64-hex",
    "output_manifest_sha256": "64-hex",
    "output_files": []
  },
  "source_snapshot_identity": {},
  "published_artifacts": {
    "parent_blocks": {"path": "", "sha256": "64-hex", "row_count": 0},
    "story_atoms": {"path": "", "sha256": "64-hex", "row_count": 0},
    "source_refs": {"path": "", "sha256": "64-hex", "row_count": 0},
    "build_manifest": {"path": "", "sha256": "64-hex"}
  },
  "fidelity_result_sha256": "64-hex",
  "fidelity_passed": false,
  "fidelity_blocker_multiset_sha256": "64-hex",
  "classified_blocker_multiset_sha256": "64-hex",
  "test_receipts": [],
  "protected_identity_count": 32,
  "protected_drift_count": 0,
  "story_dependency_blockers": [],
  "non_story_media_blockers": [],
  "e_dependency_ready": false
}
```

`e_dependency_ready=true` 仅当：

- C8b–C9 全部验收并合并；
- 合并后重建与 fidelity 正常返回；
- `story_dependency_blockers == []`，即 Story Parent/Atom/source-ref/migration 无 blocker；
- 所有发布路径均位于 `main` 的固定 build root，哈希与行数闭合；
- 保护状态零漂移且 forbidden counters 全零。

`non_story_media_blockers` 可以保留 C8c 中证据不足的旧媒体关系，但必须逐类计数并证明不改变 Story 文本/Atom/source-ref。它们不能被重命名为“已核销”，也不能被 E 消费或用来放宽媒体运行时。

- [ ] **Step 6: 绑定后续 D0**

D0.2、D0.3 和 D0.4 必须接收 `c-release-receipt.v1.json` 的绝对路径及期望 SHA-256，重新验证 schema、artifact hashes 和 `e_dependency_ready=true`。合并祖先关系必须实际执行：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $CReleaseReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedCReleaseReceiptSha256
)

$Project = 'D:\1999Wiki'
$ObservedReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $CReleaseReceiptPath).Hash.ToLowerInvariant()
if ($ObservedReceiptSha -ne $ExpectedCReleaseReceiptSha256.ToLowerInvariant()) {
  throw 'C release receipt hash mismatch'
}
$CRelease = Get-Content -Raw -LiteralPath $CReleaseReceiptPath | ConvertFrom-Json
if ($CRelease.schema_version -ne 'rag.thread-c-release/v1' -or -not $CRelease.e_dependency_ready) {
  throw 'C release receipt is not E-ready'
}
$CMergeCommit = [string]$CRelease.c_merge_commit
git -C $Project merge-base --is-ancestor $CMergeCommit HEAD
if ($LASTEXITCODE -ne 0) { throw 'C merge commit is not an ancestor of HEAD' }
```

`$CMergeCommit` 必须由已验证 receipt 解析，不得手填。任一不符时停止；不得重新从 C worktree 补取文件。

---

## 4. D0：监督器与评测基线

### Task D0.1：升级监督器为独立 E worker

**Spec coverage:** `THREAD-P0-05` 至 `THREAD-P0-10`、`SUPERVISOR-P0-01` 至 `SUPERVISOR-P0-04`、`REVIEW-P0-01`、`REVIEW-P0-02`

**Files:**

- Modify: `config/codex-supervisor.workers.json`
- Modify: `src/codex_supervisor/contracts.py`
- Modify: `src/codex_supervisor/cli.py`
- Modify: `src/codex_supervisor/processes.py`
- Modify: `src/codex_supervisor/runner.py`
- Create: `src/codex_supervisor/task_receipts.py`
- Modify: `scripts/codex-supervisor/Start-Worker.ps1`
- Modify: `scripts/codex-supervisor/Resume-Worker.ps1`
- Modify: `scripts/codex-supervisor/Stop-Worker.ps1`
- Modify: `scripts/codex-supervisor/Watch-Worker.ps1`
- Modify: `scripts/codex-supervisor/Open-SupervisorWindows.ps1`
- Modify: `scripts/codex-supervisor/Show-Dashboard.ps1`
- Create: `scripts/codex-supervisor/Write-TaskReceipt.ps1`
- Modify: `tests/test_codex_supervisor_contracts.py`
- Modify: `tests/test_codex_supervisor_cli.py`
- Modify: `tests/test_codex_supervisor_processes.py`
- Modify: `tests/test_codex_supervisor_powershell.py`
- Modify: `tests/test_codex_supervisor_e2e.py`
- Create: `tests/test_codex_supervisor_task_receipts.py`

**Frozen interface:**

```python
SUPPORTED_WORKERS: tuple[str, ...] = ("A", "B", "C", "E")
WorkerName = Literal["A", "B", "C", "E"]

def validate_worker_name(value: object) -> WorkerName: ...
def supported_workers_json() -> dict[str, object]: ...

def compute_allowed_tree_identity(
    *,
    repository_root: Path,
    base_commit: str,
    allowed_relative_paths: Sequence[str],
) -> AllowedTreeIdentity: ...

def verify_task_receipt(receipt: Mapping[str, object]) -> None: ...
```

`AllowedTreeIdentity` 使用以下唯一算法：把 allowlist 规范化为无重复、升序 POSIX 相对路径；对每个路径记录 `state=absent|file`，file 时记录 raw-byte `size_bytes` 与小写 SHA-256；未跟踪文件和已跟踪文件同等计入，删除项以 `absent` 计入。将 `schema_version=codex.allowed-tree-identity/v1`、`base_commit` 和完整 entries 用 UTF-8、keys 升序、无额外空白的 canonical JSON 编码后取 SHA-256。目录、符号链接、越出仓库路径、allowlist 外变化或同路径不同大小/哈希均拒绝。

CLI：

```text
codex-supervisor worker-list --json
codex-supervisor worker-validate --worker E --json
```

PowerShell 脚本不得保留 `ValidateSet("A","B","C","E")` 或独立数组；它们调用 `worker-validate`，窗口启动器调用 `worker-list`。

- [ ] **Step 1: 写 RED tests**

测试必须先证明：

- v1 配置被明确拒绝，v2 必须精确包含 A/B/C/E；
- A/B/C 既有 state 路径和内容原样读取，不重写迁移；
- E 使用独立 branch、worktree、state、event、stderr、session、lock；
- Python CLI 和六个 PowerShell 入口只消费公共 worker list；
- `running + pid=null` 不被 status/inspect 判定为可信存活；
- E 观察窗口关闭后 worker 仍在；
- E 原 session 可恢复；
- E 不能映射到 C 的目录或 session；
- RED/GREEN tree identity 包含 allowlist 内未跟踪测试和实现文件；
- 相同 base/bytes 生成相同 canonical identity，absent/file、额外文件或日志哈希漂移均被拒绝；
- D 的 RED acceptance 必须绑定 pre-implementation tree identity 与 RED log SHA-256。

Run RED:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_codex_supervisor_task_receipts.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-supervisor-red-' + [Guid]::NewGuid().ToString('N')))
```

Expected: v2/E/public-worker-list 测试因当前只支持 A/B/C 而失败；task receipt 测试因 canonical tree identity 与 RED acceptance contract 尚不存在而失败。

- [ ] **Step 2: 实现唯一 worker 集合、配置 v2 与 task receipt**

只替换 worker identity/config/CLI/PowerShell 验证来源，并实现独立的 canonical tree/task receipt 模块；不重构事件归约、状态语义或 token 统计。

- [ ] **Step 3: 运行 GREEN 与相邻回归**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_codex_supervisor_events.py `
  tests/test_codex_supervisor_task_receipts.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-supervisor-green-' + [Guid]::NewGuid().ToString('N')))
```

Expected: exit code 0。

- [ ] **Step 4: 静态拒绝手写集合**

```powershell
rg -n 'A.*B.*C|ValidateSet|choices=' `
  src/codex_supervisor `
  scripts/codex-supervisor
```

逐项确认所有命中只剩 `SUPPORTED_WORKERS` 定义、测试预期或与 worker 无关的文本。

- [ ] **Step 5: 提交**

```powershell
git diff --check
git add -- `
  config/codex-supervisor.workers.json `
  src/codex_supervisor/contracts.py `
  src/codex_supervisor/cli.py `
  src/codex_supervisor/processes.py `
  src/codex_supervisor/runner.py `
  src/codex_supervisor/task_receipts.py `
  scripts/codex-supervisor/Start-Worker.ps1 `
  scripts/codex-supervisor/Resume-Worker.ps1 `
  scripts/codex-supervisor/Stop-Worker.ps1 `
  scripts/codex-supervisor/Watch-Worker.ps1 `
  scripts/codex-supervisor/Open-SupervisorWindows.ps1 `
  scripts/codex-supervisor/Show-Dashboard.ps1 `
  scripts/codex-supervisor/Write-TaskReceipt.ps1 `
  tests/test_codex_supervisor_contracts.py `
  tests/test_codex_supervisor_cli.py `
  tests/test_codex_supervisor_processes.py `
  tests/test_codex_supervisor_powershell.py `
  tests/test_codex_supervisor_e2e.py `
  tests/test_codex_supervisor_task_receipts.py
git commit -m "feat(codex): add supervised story segment worker"
```

### Task D0.2：冻结 Story gold、等价 Atom 匹配器和阈值

**Spec coverage:** `EVALSET-P0-01` 至 `EVALSET-P0-18`、`EVAL-P0-01` 至 `EVAL-P0-03`、`GATE-P0-01` 至 `GATE-P0-06`、`REVIEW-P0-04`、`REVIEW-P0-09` 至 `REVIEW-P0-12`

**Files:**

- Modify: `.gitignore`
- Create: `src/rag_eval/story_segment_baseline.py`
- Create: `scripts/capture_story_segment_baseline.py`
- Create: `tests/test_story_segment_baseline.py`
- Create: `eval/story_segment_eval.v1.jsonl`
- Create: `eval/story_segment_thresholds.v1.json`
- Read-only required input: accepted C release receipt and its published Story Atom artifact

- [ ] **Step 0: 只开放四个版本化 eval 文件**

在现有 `eval/*` 规则后增加且只增加：

```gitignore
!eval/story_segment_eval.v1.jsonl
!eval/story_segment_thresholds.v1.json
!eval/story_baseline_atom_equivalence.v1.jsonl
!eval/story_segment_baseline_receipt.v1.json
```

不得开放 `eval/story_segment/`、run/handoff/receipt 临时目录或其他 `eval/*`。创建文件后逐项执行 `git check-ignore --no-index -q -- <path>`，四个版本化文件都必须返回非零；另用一个 `eval/story_segment/runs/probe.json` 证明普通运行产物仍被 ignore。

同一步先重验 C release receipt；gold 中每个 Atom ID/path/hash 必须来自 receipt 固定的合并后 Story Atom artifact。C release 未通过或 artifact hash 不符时，本 Task 不得创建 gold。

**Frozen baseline API:**

```python
@dataclass(frozen=True)
class AtomEvidenceTarget:
    query_id: str
    atom_id: str
    required_atom_group: str
    source_title: str
    source_json_path: str
    source_content_sha256: str
    normalized_evidence_sha256: str

@dataclass(frozen=True)
class AtomEquivalenceMatch:
    query_id: str
    stage: Literal["retrieval_at_k", "final_context"]
    result_rank: int
    atom_id: str
    match_rule: Literal[
        "exact_atom_id",
        "exact_source_path_revision_hash",
        "unique_exact_text_span",
        "unmatched",
        "ambiguous",
    ]
    matched_span: tuple[int, int] | None
    matched: bool
    reason_code: str

def match_active_evidence_to_atoms(
    active_results: Sequence[Mapping[str, object]],
    gold_atoms: Sequence[AtomEvidenceTarget],
    *,
    stage: Literal["retrieval_at_k", "final_context"],
) -> tuple[AtomEquivalenceMatch, ...]: ...
```

匹配顺序严格为：

1. exact Atom ID；
2. exact source JSON path + 同 source revision/content hash；
3. 同来源版本中的唯一规范证据文本 span；
4. 否则 unmatched/ambiguous。

一个活动 span 最多消费一次；migration expansion group 本身不产生覆盖。

- [ ] **Step 1: 写 baseline matcher RED tests**

覆盖：

- 精确 Atom ID；
- 精确 path/revision/hash；
- 唯一 exact text span；
- 重复文本歧义；
- source version 不同；
- 仅有 migration group；
- 空 source ref；
- Unicode/空白规范化边界；
- 同一 span 不可消费多个 Atom；
- `retrieval_at_k` 与 `final_context` 完全隔离；
- LLM answer、Planner rewrite 和 summary 永不作为覆盖证据。

Run RED:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_baseline.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-baseline-red-' + [Guid]::NewGuid().ToString('N')))
```

Expected: import/contract tests fail because matcher does not exist。

- [ ] **Step 2: 实现最小 matcher 与 canonical receipt**

Receipt 按 `query_id, stage, rank, atom_id` 排序；JSON 使用 UTF-8、sorted keys、有限数字和 LF。

- [ ] **Step 3: 冻结评测集**

`eval/story_segment_eval.v1.jsonl` 至少包含：

- 精确对白/专名/内部 ID；
- `6`、`37` 和其他纯数字或短实体；
- 单 Story 局部事实；
- 单 Story 多细节；
- 中后段剧情事实；
- “伊索尔德是在哪一章出现的”；
- “伊索尔德是怎么疯掉的”；
- 显式 2、3、4、5、32、33 Story；
- 角色技能 + Story 介绍复合请求；
- Story continuation 与 anchor；
- `暴雨是什么` Topic 定义；
- Story 例证补充分支；
- 分支互斥、汇合和 cycle；
- oversize Atom；
- local fact、bounded multi-evidence、exhaustive narrative；
- 非 Story 的短 alias、长词子串、跨类型同名负例；
- continuation 篡改/stale/oversize action；
- `not_applicable`、failed、empty 和 mixed composite 状态。

Gold 每行必须引用同版固定 Atom artifact 身份，不写自由文本“应该差不多命中”。

- [ ] **Step 4: 冻结阈值**

`eval/story_segment_thresholds.v1.json` 逐项编码 Spec 第 26.1 节阈值、方向、零容忍属性和 denominator definition。不得使用一个 `pass_rate` 代替逐项门槛。

- [ ] **Step 5: 运行 GREEN**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_story_segment_baseline.py `
  tests/test_rag_eval_contracts.py `
  tests/test_rag_eval_deterministic.py `
  tests/test_rag_eval_scoring.py -q `
  --basetemp (Join-Path ([IO.Path]::GetTempPath()) ('1999wiki-story-d0-baseline-green-' + [Guid]::NewGuid().ToString('N')))
```

Expected: exit code 0。

- [ ] **Step 6: 提交 matcher、gold 和 thresholds**

```powershell
git diff --check
git add -- `
  .gitignore `
  src/rag_eval/story_segment_baseline.py `
  scripts/capture_story_segment_baseline.py `
  tests/test_story_segment_baseline.py `
  eval/story_segment_eval.v1.jsonl `
  eval/story_segment_thresholds.v1.json
git commit -m "test(rag): freeze story segment evaluation contracts"
```

### Task D0.3：捕获当前活动 baseline 与依赖 receipt

**Spec coverage:** `EVALSET-P0-03` 至 `EVALSET-P0-14`、`PROVENANCE-P0-01` 至 `PROVENANCE-P0-06`、`THREAD-P0-03`、`THREAD-P0-10`、`SCOPE-P0-01`、`SCOPE-P0-06`

**Files:**

- Create: `eval/story_baseline_atom_equivalence.v1.jsonl`
- Create: `eval/story_segment_baseline_receipt.v1.json`
- Read-only required input: D-owned `c-release-receipt.v1.json` and `.sha256`
- No production code change unless Task D0.2 tests reveal a separately reviewed matcher defect

- [ ] **Step 1: 验证 C release receipt 与固定依赖**

不得再用“两个 C 文档已被跟踪”替代 C 发布验证。先读取 DC0 的 receipt 路径与期望 SHA-256，验证：

```text
schema_version == rag.thread-c-release/v1
e_dependency_ready == true
c_merge_commit is an ancestor of current main
C8a/C8b/C8c/C8d commit identities match the reviewed commits
published Parent/Story Atom/source-ref/build-manifest paths are inside the fixed main build root
every published artifact size/row_count/SHA-256 matches
post-merge fidelity receipt hash matches
protected_identity_count == 32
protected_drift_count == 0
Story-text/Atom/source-ref remaining blockers == []
```

然后确认 C migration decision、closure-gates plan 和 C8d 自包含诊断入口均由该合并提交跟踪。任一项不符立即停止；不得从当前未跟踪副本、C worktree 或旧 run 目录读取实施契约或数据。

- [ ] **Step 2: 只读验证活动产物**

使用现有 provenance verifier 验证 active Parent/Child/BM25/Milvus 指针和 source snapshot。记录：

```text
path
size
row_count
sha256
schema_version
build_version
active_pointer_sha256
collection_name
collection_schema_sha256
```

- [ ] **Step 3: 捕获 baseline**

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' `
  scripts/capture_story_segment_baseline.py `
  --queries eval/story_segment_eval.v1.jsonl `
  --thresholds eval/story_segment_thresholds.v1.json `
  --equivalence-output eval/story_baseline_atom_equivalence.v1.jsonl `
  --receipt-output eval/story_segment_baseline_receipt.v1.json `
  --reranker-disabled
```

要求：

- 只读 active collection；
- 记录 retrieval-at-k 和 final-context 两种 stage；
- 不把最终答案计为 Atom evidence；
- reranker call count 为 0；
- 输出逐行 canonical；
- 不修改 active pointer、collection 或 corpus artifact。
- gold 与等价匹配只引用 C release receipt 固定的 Story Atom artifact；不得把 C 分支、旧 run 目录或旧活动聚合 Story Child 当作新 Atom 事实源。

- [ ] **Step 4: 重跑并验证字节一致**

第二次输出到新临时目录；比较两次 JSONL 和 receipt 的业务内容哈希。仅 `captured_at_utc`、run ID 等显式非身份字段允许变化，且不得进入 baseline identity。

- [ ] **Step 5: 提交 baseline**

```powershell
git diff --check
git add -- `
  eval/story_baseline_atom_equivalence.v1.jsonl `
  eval/story_segment_baseline_receipt.v1.json
git commit -m "test(rag): capture story segment active baseline"
```

### Task D0.4：创建 E worktree 并只下发已批准 E Plan

**Spec coverage:** `THREAD-P0-01` 至 `THREAD-P0-10`、`SUPERVISOR-P0-01` 至 `SUPERVISOR-P0-04`

**Files:**

- Runtime only: `.codex-supervisor/workers/E/approved-task.md`
- Runtime only: `.codex-supervisor/workers/E/dependency-receipt.v1.json`
- No tracked source change

- [ ] **Step 1: 生成 D0 dependency receipt**

Receipt 必须包含：

```text
main_commit
spec_commit/spec_sha256
D Plan sha256
E Plan sha256
C release receipt path/sha256/schema
C8a/C8b/C8c/C8d/C9 and C merge commit identities
C post-merge fidelity and published Parent/Story Atom/source-ref artifact sha256
gold/threshold/baseline receipt sha256
Conda interpreter/version/prefix
reranker disabled
approved branch/worktree
```

Receipt 生成器必须重新验证 C release receipt 和所有发布 artifact；不得只复制其中字段。`main_commit` 必须包含 `c_merge_commit`，且与即将创建 E worktree 的基线完全相同。

- [ ] **Step 2: 验证目标路径**

解析绝对路径并确认：

```text
D:\1999Wiki.worktrees\rag-e-story-segment
```

不存在同名脏 worktree、branch 或 supervisor state。若存在，停止并审计；不得删除或覆盖。

- [ ] **Step 3: 创建 worktree**

```powershell
$EBaseCommit = (git rev-parse HEAD).Trim()
git worktree add `
  -b codex/rag-e-story-segment `
  'D:\1999Wiki.worktrees\rag-e-story-segment' `
  $EBaseCommit
```

创建后立即验证 E 的 `HEAD == $EBaseCommit`，并在 E worktree 中重新读取 D0 receipt；若 C release receipt 或任一发布 artifact 哈希不同，删除动作不获授权，E 保持未启动并报告 blocker。

- [ ] **Step 4: 写 approved task**

任务必须引用已提交的 E Plan、Spec、D0 receipt，明确：

```text
Plan phase: E0 only
Subagents: forbidden
Embedding API: forbidden
Milvus writes: forbidden
Production activation: forbidden
Allowed files: E0 allowlist only
Stop state: completed_pending_review
```

- [ ] **Step 5: 启动并验证可观察性**

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File 'D:\1999Wiki\scripts\codex-supervisor\Start-Worker.ps1' `
  -Worker E
```

重新打开观察窗口命令：

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass `
  -File 'D:\1999Wiki\scripts\codex-supervisor\Watch-Worker.ps1' `
  -Worker E
```

关闭观察窗口后用 OS PID/create-time、event log 最后时间和 state heartbeat 三项确认 worker 仍运行。

---

## 5. E 阶段监督门

### Task D1：逐 Task 接受 E0–E5

**Files:** no implementation edits in D

E0.0 是不提交的 preflight。E0.1–E5.3 共 16 个 implementation Task 都是阶段内的独立小门，必须按以下顺序：

1. E 只在已批准测试文件内写 RED test，不写实现，并停在 `red_pending_d_witness`。
2. E 运行表中精确 RED argv，保存 raw log，使用 D0.1 的 canonical 算法计算包含未跟踪测试文件的 `red_tree_identity`。
3. D 在同一未实现 tree 上检查 allowlist/diff，独立复跑同一 RED argv；只有观察到表中业务失败后，D 才写 hash-pinned `rag.story-segment-red-acceptance/v1`，固定 task/base、E/D RED logs、`red_tree_identity` 和预期/实际失败。收集错误、环境错误或测试名不存在均拒绝。
4. D 将 RED acceptance 路径/SHA-256 写入 resume 指令，才允许 E 做最小实现和运行阶段 GREEN。
5. E 运行该阶段规定的相邻回归和真实证据门，计算 `green_tree_identity` 与 GREEN log SHA-256。
6. E 写 `rag.story-segment-task-receipt/v1`，分别固定 RED/GREEN tree/log、D RED acceptance、真实证据 required/not_applicable、protected drift、forbidden counters 和文件范围。
7. E 停在 `completed_pending_review`，不提交下一阶段。
8. D 独立检查：
   - `git diff --check`
   - `git diff --name-only`
   - `git status --short`
   - 代码与 Spec contract
   - E 的测试命令
   - 真实快照证据和 protected pre/post
   - forbidden operation counters
9. D 重算 task receipt/tree/log/RED acceptance hashes，复跑 GREEN suite，并核对真实证据或表中明确的 `not_applicable` 理由。D 不在实现后把已转绿的 test 伪称为 RED 复跑。
10. D 接受后才允许精确 Task 提交。下一 Task 使用同一 E worktree；若 session 上下文过重，可在 Task 提交后新开 E session，但仍只有一个 E worker。

每份 D RED acceptance 使用：

```json
{
  "schema_version": "rag.story-segment-red-acceptance/v1",
  "task_id": "E0.1",
  "base_commit": "40-hex",
  "allowed_tree_identity_sha256": "64-hex",
  "allowed_tree_manifest_sha256": "64-hex",
  "expected_business_failure": "",
  "e_red": {"argv": [], "exit_code": 1, "log_sha256": "64-hex", "observed_failure": ""},
  "d_red": {"argv": [], "exit_code": 1, "log_sha256": "64-hex", "observed_failure": ""},
  "observed_changed_files": [],
  "outside_allowlist_change_count": 0,
  "accepted_at_utc": "RFC3339 UTC",
  "d_supervision_commit": "40-hex"
}
```

Acceptance 写入后即不可变；E 的 resume prompt 只携带路径和期望 SHA-256。若 tree、base、argv、日志或 allowlist 后续变化，必须废弃本次 acceptance 并从新的 RED gate 开始，不能在原 receipt 上补字段。

D 不接受：

- 只报测试数量、不提供命令和新鲜输出；
- fixture 通过但真实快照闭包失败；
- 为旧 schema 猜测兼容 Segment；
- 将 `segment_id` 填入 `child_id`；
- 放宽 Owner Gate；
- 通过质量硬标签删除短/数字内容；
- 在 E 中调用真实 embedding 或 Milvus；
- 未经审查将多个阶段堆进一个提交。

### Task D2：审查 E5 handoff

- [ ] **Step 1: 验证 E 分支提交链**

要求 E0.0 只有预检 receipt、不提交；E0.1–E5.3 共 16 个 implementation Task 各有一个独立、可追踪提交。提交不得包含 ignored real-run outputs、原始 snapshot、pytest basetemp、supervisor state 或用户文件。

- [ ] **Step 2: 验证 handoff schema 和哈希**

重算所有文件 SHA-256、row count、ordered ID hash、schema hash 和 config identity。

- [ ] **Step 3: 验证 typed Dense 行集合**

必须证明：

```text
all non-Story Child -> retrieval_unit_type=child
all Story Segment -> retrieval_unit_type=story_segment
no Story Atom -> typed Dense input
no segment_id copied into child_id
retrieval_unit_id globally unique
exact field is segment_sequence_index; segment_sequence is absent
child segment_sequence_index == -1; story_segment chunk_index == -1
text length <= 16384
reranker call count == 0
```

- [ ] **Step 4: 验证无外部漂移**

比较 protected pre/post：

- active pointer；
- active Milvus collection/schema/row count；
- source snapshot；
- active BM25；
- MinIO/MySQL 状态；
- runtime config；
- production provenance。

任何 drift 阻断合并。

- [ ] **Step 5: 固化 D-owned handoff intake**

E handoff 只能在 E5.3 已提交、E HEAD clean 且 `e_commit == HEAD` 后生成。D 将 handoff 列出的文件逐个复制到 create-new ignored 目录：

```text
eval/story_segment/intake/<run-id>/
```

随后重算 SHA-256，并写 `d-e-handoff-intake.v1.json`。Receipt 固定 E branch/commit、原 handoff path/hash、复制后相对路径/hash/size、typed artifact、candidate-build-input、离线容量估算、test/protected receipts。此时不存在真实 collection，因此 intake 不得声称包含最终 runtime snapshot。后续 D3–D5 只消费 intake，不再依赖 E worktree 文件；E worktree 的后续变化使 intake 作废。

---

## 6. D 合并与真实向量影子构建

### Task D3：合并 E 到 main 并运行合并后回归

**Spec coverage:** `THREAD-P0-02`、`THREAD-P0-04`、`REVIEW-P0-01` 至 `REVIEW-P0-18`

- [ ] **Step 1: 保存 main 用户工作区边界**

记录 `git status --short`，确认用户文件不与 E 提交冲突。不得 stash、reset、checkout 或删除用户改动。

- [ ] **Step 2: 审查 E 提交**

```powershell
git log --oneline --decorate --no-merges main..codex/rag-e-story-segment
git diff --stat main...codex/rag-e-story-segment
git diff --check main...codex/rag-e-story-segment
```

- [ ] **Step 3: 合并**

使用非破坏性 merge。发生冲突时只解决 E 与已批准 D0 代码的真实冲突；不改无关用户文件。

- [ ] **Step 4: 运行 E Plan 的完整测试矩阵**

使用 OS 临时目录下的 create-new basetemp，至少包含 supervisor、build、runtime artifacts、BM25、vectorstore、request plan、route policy、retriever、budget、citations、execution、conversation、serializer、backend、SSE、frontend 和 rag_eval。

- [ ] **Step 5: 创建合并后 candidate-build-input**

在 create-new build version 下离线重建 Story structure、Segment 和 typed Dense JSONL；比较 E handoff 的 schema/config identity，允许数据 build version 变化但不允许算法身份漂移。本步骤只生成 `rag.story-candidate-build-input/v1`，因为真实 collection 尚不存在；禁止生成 `rag.runtime-artifact-snapshot/v2`。

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $DIntakeReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedDIntakeReceiptSha256,
  [Parameter(Mandatory = $true)]
  [string] $CReleaseReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedCReleaseReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$CandidateRunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$CandidateRunRoot = Join-Path 'D:\1999Wiki\eval\story_segment\runs' $CandidateRunId
$ObservedDIntakeSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $DIntakeReceiptPath).Hash.ToLowerInvariant()
$ObservedCReleaseSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $CReleaseReceiptPath).Hash.ToLowerInvariant()
if ($ObservedDIntakeSha -ne $ExpectedDIntakeReceiptSha256.ToLowerInvariant()) {
  throw 'D handoff intake hash mismatch'
}
if ($ObservedCReleaseSha -ne $ExpectedCReleaseReceiptSha256.ToLowerInvariant()) {
  throw 'C release receipt hash mismatch'
}
& $Python scripts/build_story_segment_candidate.py `
  --handoff-intake $DIntakeReceiptPath `
  --expected-handoff-intake-sha256 $ExpectedDIntakeReceiptSha256 `
  --c-release-receipt $CReleaseReceiptPath `
  --expected-c-release-receipt-sha256 $ExpectedCReleaseReceiptSha256 `
  --output-root $CandidateRunRoot `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Candidate build-input generation failed' }
```

命令必须在 embedding provider/Milvus constructor 之前退出，输出：

```text
candidate-build-input.v1.json
candidate-build-input.v1.sha256
deployment-inventory.v1.json
offline-capacity-estimate.v1.json
candidate-build-receipt.v1.json
```

D 重新验证 candidate-build-input 的完整 artifact tuple、expected typed collection schema、typed input、C/D0/E identities 和 protected state。命令还必须把 D intake 固定的 deployment inventory 复制为同一 candidate root 内的不可变 `deployment-inventory.v1.json`，并在 `rag.story-candidate-build-receipt/v1` 中记录相对路径/SHA-256。`candidate-build-input.v1.json` 必须由该命令实际生成，不能手工拼接；其 schema 明确禁止 actual collection name、observed schema、observed row count 和 shadow build receipt。

`deployment-inventory.v1.json` 的 Milvus/RBAC 部分是唯一授权事实源，必须由 D intake producer 机器生成并由 D3 原字节复制，不允许 D3、D4 或 E 手填、补默认值或从 `describe_role()` 结果反推策略。它至少精确固定：remote host 与 host-key fingerprint、三个允许的绝对 storage path 及预期 device、Milvus URI/database/principal、允许的精确 role 集、以及每项允许 grant 的 `role_name/database/object_type/object_name/privilege` 五元组。`object_name` 可以是本轮唯一 `$ShadowCollection` 的受约束模板；database/global wildcard 只有在 inventory 中作为完整五元组显式列出时才被接受。D4 只把 read-only observed RBAC facts 与这些五元组比较；主体、role、database、object type/name、privilege 任一缺失、未知或超出 allowlist 均 fail-closed。D intake 缺少该 exact schema 时不得生成 E5.3 的真实 handoff、进入 D3 或执行 D4，也不得在 D4 临时补写；E2.2 只能使用同 schema 的 synthetic fixture 实现与测试 parser/preflight。

### Task D4：预检并执行一次 Typed Dense shadow build

**Spec coverage:** `INDEX-P0-01` 至 `INDEX-P0-06`、`DENSEUNIT-P0-01` 至 `DENSEUNIT-P0-11`、`PERF-P0-01` 至 `PERF-P0-09`、`PROVENANCE-P0-01` 至 `PROVENANCE-P0-06`

**External write authorization:** 仅本任务可调用 embedding API 和创建新 Milvus shadow collection。仍禁止 active pointer、生产激活、active collection 覆盖或删除。

- [ ] **Step 1: 从 D3 receipt 固定运行身份**

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $CandidateBuildReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedCandidateBuildReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$RunId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$RunRoot = Join-Path 'D:\1999Wiki\eval\story_segment\shadow-runs' $RunId
$null = New-Item -ItemType Directory -Path $RunRoot
$ObservedBuildReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $CandidateBuildReceiptPath).Hash.ToLowerInvariant()
if ($ObservedBuildReceiptSha -ne $ExpectedCandidateBuildReceiptSha256.ToLowerInvariant()) {
  throw 'Candidate build receipt hash mismatch'
}
$CandidateReceipt = Get-Content -Raw -LiteralPath $CandidateBuildReceiptPath | ConvertFrom-Json
if ($CandidateReceipt.schema_version -ne 'rag.story-candidate-build-receipt/v1') {
  throw 'Unexpected candidate build receipt schema'
}
$CandidateRoot = Split-Path -Parent $CandidateBuildReceiptPath
$CandidateBuildInput = [IO.Path]::GetFullPath(
  (Join-Path $CandidateRoot ([string]$CandidateReceipt.candidate_build_input.relative_path))
)
$CandidateBuildInputSha = [string]$CandidateReceipt.candidate_build_input.sha256
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $CandidateBuildInput).Hash.ToLowerInvariant() -ne $CandidateBuildInputSha) {
  throw 'Candidate build input hash mismatch'
}
$DeploymentInventoryPath = [IO.Path]::GetFullPath(
  (Join-Path $CandidateRoot ([string]$CandidateReceipt.deployment_inventory.relative_path))
)
$ExpectedDeploymentInventorySha256 = [string]$CandidateReceipt.deployment_inventory.sha256
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $DeploymentInventoryPath).Hash.ToLowerInvariant() -ne $ExpectedDeploymentInventorySha256) {
  throw 'Deployment inventory hash mismatch'
}
$ShadowCollection = "huiji_story_segment_shadow_$RunId"
```

Candidate receipt 必须来自 D3，schema 为 `rag.story-candidate-build-receipt/v1`，并固定 typed JSONL/schema、row/order hashes、expected Milvus schema、embedding identity、source/artifact/config identities。`$ShadowCollection` 是本阶段唯一新 collection 名。

- [ ] **Step 2: 生成远端存储容量 receipt**

在构造 embedding provider 或 Milvus client 前，用 hash-pinned deployment inventory 中的 SSH 目标和 host-key fingerprint 对真实服务器做只读探针：

```powershell
$RemoteCapacityReceipt = Join-Path $RunRoot 'remote-storage-capacity.v1.json'
& $Python scripts/probe_story_segment_storage.py `
  --candidate-build-input $CandidateBuildInput `
  --expected-candidate-build-input-sha256 $CandidateBuildInputSha `
  --deployment-inventory $DeploymentInventoryPath `
  --expected-deployment-inventory-sha256 $ExpectedDeploymentInventorySha256 `
  --remote-path /srv/1999wiki/milvus `
  --remote-path /srv/1999wiki/rag-artifacts `
  --remote-path /srv/1999wiki/import-staging `
  --max-story-segment-rows 25000 `
  --minimum-projected-free-bytes 12884901888 `
  --receipt-ttl-seconds 900 `
  --output $RemoteCapacityReceipt
if ($LASTEXITCODE -ne 0) { throw 'Remote storage capacity gate failed' }
$RemoteCapacityReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $RemoteCapacityReceipt).Hash.ToLowerInvariant()
```

`rag.story-shadow-storage-capacity/v1` 固定 probe UTC、TTL、远端 host identity/host-key fingerprint、每个路径的 resolved path/device ID/free bytes、active + shadow vectors + index metadata + staging + safety margin 的逐设备峰值公式、Story Segment/typed row count 和 projected free bytes。若三个目录跨设备，分别计算各设备峰值；不得把本机 `D:` 空间当作云端容量。硬门为 Story Segment `<=25000` 且所有受影响远端设备构建后 projected free `>=12 GiB`。未知、stale、路径缺失、device 不明或输入不闭合均失败；本步骤的 embedding/Milvus client/write 计数必须为 0。

- [ ] **Step 3: 生成只读 Milvus preflight receipt**

仅在 Step 2 receipt 通过并重验后，允许构造只读 Milvus client：

```powershell
$MilvusPreflightReceipt = Join-Path $RunRoot 'milvus-preflight.v1.json'
& $Python scripts/build_huiji_typed_index.py milvus-preflight `
  --candidate-build-input $CandidateBuildInput `
  --expected-candidate-build-input-sha256 $CandidateBuildInputSha `
  --remote-capacity-receipt $RemoteCapacityReceipt `
  --expected-remote-capacity-receipt-sha256 $RemoteCapacityReceiptSha `
  --deployment-inventory $DeploymentInventoryPath `
  --expected-deployment-inventory-sha256 $ExpectedDeploymentInventorySha256 `
  --collection-name $ShadowCollection `
  --max-capacity-receipt-age-seconds 900 `
  --receipt-ttl-seconds 300 `
  --receipt $MilvusPreflightReceipt `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Milvus read-only preflight failed' }
$MilvusPreflightReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $MilvusPreflightReceipt).Hash.ToLowerInvariant()
```

`rag.story-shadow-milvus-preflight/v1` 必须证明 collection 不存在且不与 active/forbidden inventory 重叠、目标 database/schema 与 RBAC create/insert/index privilege 可见、active pointer/config/inventory 已 hash-pinned、read-only write count 为 0。权限不能只读证明时 fail-closed，不得以试建 collection 探测。

- [ ] **Step 4: 执行一次 shadow build 并生成最终 v2 snapshot**

只有两个 receipt 都通过、仍在 TTL 内且其输入 identity 完全一致后，才允许验证 embedding 凭证并构造 embedding provider/写 Milvus client：

```powershell
& $Python scripts/build_huiji_typed_index.py build `
  --candidate-build-input $CandidateBuildInput `
  --expected-candidate-build-input-sha256 $CandidateBuildInputSha `
  --remote-capacity-receipt $RemoteCapacityReceipt `
  --expected-remote-capacity-receipt-sha256 $RemoteCapacityReceiptSha `
  --milvus-preflight-receipt $MilvusPreflightReceipt `
  --expected-milvus-preflight-receipt-sha256 $MilvusPreflightReceiptSha `
  --deployment-inventory $DeploymentInventoryPath `
  --expected-deployment-inventory-sha256 $ExpectedDeploymentInventorySha256 `
  --collection-name $ShadowCollection `
  --max-capacity-receipt-age-seconds 900 `
  --max-milvus-preflight-receipt-age-seconds 300 `
  --receipt-root $RunRoot `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Typed Dense shadow build failed' }
```

脚本必须 create-new collection，按 typed retrieval-unit 顺序调用 embedding，写后验证 row count、PK uniqueness、observed schema、类型计数与边界样本；失败时保留 shadow 和 failure receipt，不自动 drop，不改 runtime config/active pointer。

成功后才写：

```text
shadow-build-receipt.v1.json
active-control-runtime-snapshot.v1.json
runtime-artifact-snapshot.v2.json
runtime-artifact-snapshot.v2.sha256
```

`active-control-runtime-snapshot.v1.json` 是当前合并提交中 active-v1 resolver 生成的不可变 source bytes 的逐字节副本，不修改 active pointer。E2.2 必须提供单一 `resolve_active_runtime_snapshot_source_v1(cfg)` 接口：同一次调用返回已验证的 `RuntimeArtifactSnapshot` 与 exact `rag.active-control-runtime-snapshot/v1` canonical bytes；bytes 只由该次 resolver 已验证的 active pointer、runtime config、artifact tuple、collection identity 和 source raw-byte hashes 产生。Builder 必须在任何 embedding/Milvus 写调用前捕获这一份 bytes，之后只能原样写出，禁止从 dataclass、typed-v2 字段或第二次序列化重建。写后再次运行 resolver，并要求 source bytes、active pointer、config 与 collection inventory identities 全部逐字节/逐哈希相等。最终 `rag.runtime-artifact-snapshot/v2` 固定实际 collection 名、observed schema fingerprint、observed row/type counts、embedding build identity、ordered PK hash、shadow build receipt SHA-256 和 protected active inventory；缺任一项不得生成成功 snapshot。

- [ ] **Step 5: 验证并固化 build receipt**

D 重验 retrieval-unit type counts、nullable/sentinel invariants、vector dimension、text/metadata limits、row count、PK uniqueness、artifact identity、实际 collection schema、最终 v2 snapshot 及 active collection 零漂移。成功 `rag.story-shadow-build-receipt/v1` 使用一个精确字段集：既有 candidate/collection/schema/row/type/embedding/ordered-PK/active-control 字段之外，必须包含 `status="succeeded"`、`protected_state_before`、`protected_state_after` 与 `execution_observations`。`execution_observations` 又使用 exact schema，分别记录 embedding 与 Milvus 的 API call count、batch count、最大 batch size、有限 retry count、token-safe input 上限、各阶段 monotonic elapsed milliseconds、分页验证次数，以及写后 count/PK/type/schema closure；不得把这些事实放入未受校验的自由字典。Resolver 与测试 fixture 只接受这一套字段集。Receipt 不得反向固定 candidate-v2 runtime snapshot；最终 v2 snapshot 单向固定 receipt 的相对路径与 raw-byte SHA-256，固定文件名 `runtime-artifact-snapshot.v2.sha256` 再固定 snapshot 的 raw-byte SHA-256，禁止两个 JSON 互相包含对方最终 raw-byte SHA-256。

`$RunRoot` 在 build 前已经存在，并包含 hash-pinned storage 与 Milvus preflight receipts；Builder 不得因此拒绝整个目录。它必须在任何 provider/client/外部调用前重验 RunRoot containment、拒绝 symlink/reparse escape，并以 create-new/exclusive 语义独占四个最终输出文件名以及 failure-receipt 文件名；已存在任一目标文件即 fail-closed，且不得覆盖 receipt。真实 collection 仍为 create-new，检查与创建之间的 race 也必须报告 AlreadyExists。构建失败时按本计划保留已创建的 shadow collection并发布 create-new failure receipt，禁止自动 drop；active pointer/config/active collection 始终零漂移。

### Task D5：运行真实评测并生成 go/no-go

**Spec coverage:** 全部 `EVAL-*`、`EVALSET-*`、`GATE-*`、`PERF-*`、`ANSWER-*`、`QUALITY-*`，以及第 26.1 节全部阈值

- [ ] **Step 0: 同提交、同机性能控制**

在当前合并提交、同一机器、相同进程配置、相同 query set 和相同计时器下分别运行：

```text
active v1 control: >= 1 warmup + 5 timed samples/query
typed Story v2 candidate: >= 1 warmup + 5 timed samples/query
```

不得把 D0 在旧提交捕获的语义 baseline 延迟当作性能对照。使用 E5.1 提交的固定 producer：

```powershell
param(
  [Parameter(Mandatory = $true)]
  [string] $ShadowBuildReceiptPath,
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[0-9a-fA-F]{64}$')]
  [string] $ExpectedShadowBuildReceiptSha256
)

$Python = 'D:\Anaconda32024\envs\1999wiki\python.exe'
$ObservedBuildSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ShadowBuildReceiptPath).Hash.ToLowerInvariant()
if ($ObservedBuildSha -ne $ExpectedShadowBuildReceiptSha256.ToLowerInvariant()) {
  throw 'Shadow build receipt hash mismatch'
}
$BuildReceipt = Get-Content -Raw -LiteralPath $ShadowBuildReceiptPath | ConvertFrom-Json
$BuildRoot = Split-Path -Parent $ShadowBuildReceiptPath
$ActiveRuntimeSnapshot = [IO.Path]::GetFullPath(
  (Join-Path $BuildRoot ([string]$BuildReceipt.active_control_snapshot.relative_path))
)
$ActiveRuntimeSnapshotSha = [string]$BuildReceipt.active_control_snapshot.sha256
$CandidateRuntimeSnapshot = [IO.Path]::GetFullPath(
  (Join-Path $BuildRoot 'runtime-artifact-snapshot.v2.json')
)
$CandidateRuntimeSnapshotShaFile = [IO.Path]::GetFullPath(
  (Join-Path $BuildRoot 'runtime-artifact-snapshot.v2.sha256')
)
$CandidateRuntimeSnapshotSha = (Get-Content -Raw -LiteralPath $CandidateRuntimeSnapshotShaFile).Trim().ToLowerInvariant()
if ($CandidateRuntimeSnapshotSha -notmatch '^[0-9a-f]{64}$') {
  throw 'Candidate runtime snapshot SHA-256 sidecar is invalid'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $ActiveRuntimeSnapshot).Hash.ToLowerInvariant() -ne $ActiveRuntimeSnapshotSha) {
  throw 'Active control snapshot hash mismatch'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $CandidateRuntimeSnapshot).Hash.ToLowerInvariant() -ne $CandidateRuntimeSnapshotSha) {
  throw 'Candidate runtime snapshot hash mismatch'
}
$CandidateSnapshot = Get-Content -Raw -LiteralPath $CandidateRuntimeSnapshot | ConvertFrom-Json
if ([string]$CandidateSnapshot.shadow_build_receipt.relative_path -ne 'shadow-build-receipt.v1.json') {
  throw 'Candidate runtime snapshot receipt path mismatch'
}
if ([string]$CandidateSnapshot.shadow_build_receipt.sha256 -ne $ExpectedShadowBuildReceiptSha256.ToLowerInvariant()) {
  throw 'Candidate runtime snapshot receipt SHA-256 mismatch'
}
$PerformanceReceipt = Join-Path $BuildRoot 'performance-control.v1.json'

& $Python scripts/evaluate_story_segment_rag.py performance-control `
  --queries eval/story_segment_eval.v1.jsonl `
  --active-runtime-snapshot $ActiveRuntimeSnapshot `
  --expected-active-runtime-snapshot-sha256 $ActiveRuntimeSnapshotSha `
  --candidate-runtime-snapshot $CandidateRuntimeSnapshot `
  --expected-candidate-runtime-snapshot-sha256 $CandidateRuntimeSnapshotSha `
  --warmup-count 1 `
  --timed-samples-per-query 5 `
  --output $PerformanceReceipt `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Performance control failed' }
$PerformanceReceiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $PerformanceReceipt).Hash.ToLowerInvariant()
```

`rag.story-segment-performance-control/v1` 记录 commit、机器/CPU/内存、进程配置、query set hash、两个 runtime snapshot hashes、warmup 数、sample 数、每次原始 timing 和 P50/P95。Candidate collection 只能由已验证的最终 v2 snapshot 解析；CLI 不接受独立 collection-name 参数。

- [ ] **Step 1: 运行 candidate retrieval**

```powershell
& $Python scripts/evaluate_story_segment_rag.py evaluate `
  --queries eval/story_segment_eval.v1.jsonl `
  --thresholds eval/story_segment_thresholds.v1.json `
  --baseline eval/story_segment_baseline_receipt.v1.json `
  --equivalence eval/story_baseline_atom_equivalence.v1.jsonl `
  --runtime-snapshot $CandidateRuntimeSnapshot `
  --expected-runtime-snapshot-sha256 $CandidateRuntimeSnapshotSha `
  --shadow-build-receipt $ShadowBuildReceiptPath `
  --expected-shadow-build-receipt-sha256 $ExpectedShadowBuildReceiptSha256 `
  --performance-control-receipt $PerformanceReceipt `
  --expected-performance-control-receipt-sha256 $PerformanceReceiptSha `
  --output-root $BuildRoot `
  --reranker-disabled
if ($LASTEXITCODE -ne 0) { throw 'Story Segment evaluation failed' }
```

Evaluator 从最终 v2 snapshot 取得唯一 actual collection，并验证 snapshot 内的 shadow-build-receipt SHA-256 等于显式传入 receipt；两者不一致时 fail-closed，receipt 中重复出现的 collection name 只能作为被交叉验证的诊断字段，不能覆盖 snapshot。

- [ ] **Step 2: 验证 hard gates**

报告每项必须包含：

```text
metric
numerator
denominator
baseline
candidate
delta
threshold
direction
passed
sample_failures
```

不得只输出整体通过率。

- [ ] **Step 3: 验证零容忍项**

尤其检查：

- Owner 越权；
- 分支越界；
- 重复 Story 正文；
- Atom 引用不闭合；
- Topic/Page 必要来源丢失；
- 数字/短文本/ID 退化；
- Planner/Detector/continuation/anchor 授权错误；
- `not_applicable` 误触发 empty fallback；
- RouteDecision/REST/SSE outcome 漂移；
- 有证据 partial 被错误拒答；
- 非穷尽答案过度声称；
- baseline 等价 Atom 误计；
- oversize Atom 丢失；
- reranker/API 额外调用；
- active state drift。

- [ ] **Step 4: 生成最终判定**

任一硬门失败：

```text
decision = no_go
activation_allowed = false
```

全部硬门通过：

```text
decision = go_for_activation_review
activation_allowed = false
```

本计划永不输出 `activated=true`。

### Task D6：交付而不激活

- [ ] **Step 1: 写 D final receipt**

输出：

```text
eval/story_segment/runs/$RunId/d_final_gate.v1.json
eval/story_segment/runs/$RunId/d_final_gate.v1.sha256
eval/story_segment/runs/$RunId/protected_state_diff.v1.json
```

- [ ] **Step 2: 报告用户**

报告：

- E 合并提交；
- typed artifact 和 shadow collection 身份；
- embedding API 调用、耗时和成本可见信息；
- 逐项 go/no-go；
- 剩余 blocker；
- active pointer/config/collection 零变化；
- 是否建议另行申请激活。

- [ ] **Step 3: 停止**

不运行 `scripts/activate_huiji_candidate.py`，不切换 collection，不更新 active pointer，不删除 shadow 或 active collection。

---

## 7. D Plan 完成标准

1. C8b、C8c、C8d、C9 已分别验收，C 已合并 `main`，合并后真实 fidelity 正常返回。
2. C release receipt 固定 C 提交链、发布 Parent/Story Atom/source refs、测试、保护状态和零 Story blocker；E 不读取 C worktree。
3. 监督器 v2 由单一 worker 集合支持 A/B/C/E，A/B/C 状态兼容且 E 完全隔离。
4. E 观察窗口可关闭重开，worker 继续运行并可恢复原 session。
5. Story gold、threshold、baseline matcher 和逐 Atom receipt 在 E 实现前提交冻结。
6. E worktree 从包含 C merge、C release receipt 与 D0 的固定 main 创建。
7. E0.0 预检后，16 个 implementation Task 均有 D 在实现前见证的 RED acceptance、独立 RED/GREEN tree/log、真实证据 receipt，并由 D 审查后才提交和继续。
8. E handoff 在 E5.3 clean commit 后生成；D-owned intake 的 schema、artifact、typed row、candidate-build-input、config、测试和 protected state 闭合，不伪造未构建 runtime。
9. E 不调用 embedding/Milvus；D 合并后重建 candidate-build-input，远端容量与只读 Milvus preflight 分别通过后执行一次真实 shadow build，并在写后验证完成时生成最终 `rag.runtime-artifact-snapshot/v2`。
10. 新 collection 使用 typed retrieval unit，不包含 Story Atom Dense 行。
11. 远端存储容量 receipt 在任何 embedding/Milvus constructor 前通过；只读 Milvus preflight 仅在容量通过后运行且写计数为 0；Story Segment <=25,000 且所有受影响云端设备 projected free >=12 GiB。
12. 所有 go/no-go 指标逐项输出，不以平均分抵消硬失败。
13. Reranker 调用次数为零，质量标记不影响 P0 排序。
14. active pointer、active collection、生产配置、MinIO/MySQL 和 source snapshot 在整个流程中不变。
15. 即使结果为 go，也只进入独立激活审核，不自动发布。

---

## 8. 跨 Plan Spec 追踪

Spec 的 307 个稳定条款由 305 个 P0 和 2 个明确延后的 P1 组成。两份 Plan 共同覆盖全部 P0，并把两个 P1 固定为非目标：

| Spec 范围 | 主要 Plan 落点 |
|---|---|
| `SCOPE-P0-01..06`、`DECISION-P0-01..04`、`HIER-P0-01..03` | E0/E1；D0 依赖门和 D handoff 审查 |
| `ATOMSTRUCT-P0-01..16` | E0；D 的真实快照和 artifact 审查 |
| `SEGMENT-P0-01..06`、`BOUNDARY-P0-01..12`、`IDENTITY-P0-01..04` | E1；D deterministic rebuild |
| `CITATIONUNIT-P0-01..09` | E1/E4；D 全链引用与重复正文门 |
| `ENTITYLINK-P0-01..03`、`RELATION-P0-01..03` | E0/E3；D 精确率和分支越界门 |
| `INDEX-P0-01..06`、`DENSEUNIT-P0-01..11` | E2 adapter；D 真实 embedding/shadow build |
| `REQUESTPLAN2-P0-01..13`、`STORYBRANCH-P0-01..49`、`AUTHCTX-P0-01..06` | E3/E4；D 授权评测 |
| `PIPE-P0-01..09`、`FUSION-P0-01..09`、`CANDIDATE-P0-01..04` | E3；D 真实 retrieval 评测 |
| `OWNERBUDGET-P0-01..05`、`CONTEXTBUDGET-P0-01..08` | E3/E4；D budget/coverage 门 |
| `DETAIL-P0-01..02`、`MULTISTORY-P0-01..05`、`RELATION-P0-01..03` | E3/E4；D single/multi-story gold |
| `QUALITY-P0-01..07` | E5 shadow report；D 验证真实排序未消费 |
| `SHORTFALL-P0-01..05`、`ANSWER-P0-01..13`、`SUMMARY-P0-01..03` | E4；D answer usability/overclaim 门 |
| `FAILURE-P0-01..10` | E0–E4 fail-closed；D failure receipts |
| `PROVENANCE-P0-01..06`、`PERF-P0-01..09` | E artifact/handoff；D real build/perf |
| `EVALSET-P0-01..18`、`EVAL-P0-01..03`、`GATE-P0-01..06` | D0 baseline + E5 runner + D real go/no-go |
| `THREAD-P0-01..10`、`SUPERVISOR-P0-01..04` | D0 和双 Plan 拓扑 |
| `REVIEW-P0-01..18` | 两份 Plan 的接口、拒绝方案和 D 独立验收 |
| `DETAIL-P1-01`、`SUMMARY-P1-01` | P0 不实施；只有本轮通过后另立 Spec、评测和批准 |

该表是责任路由；线程 E Plan 的逐任务追踪矩阵必须把每个范围进一步落到具体测试和失败表现。
