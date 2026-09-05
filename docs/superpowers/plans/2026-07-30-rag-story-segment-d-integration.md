# 线程 D：剧情 Segment 前置门、集成与向量影子构建 Implementation Plan

> **当前执行依据：** 先执行下方 2026-09-05 收敛修订。保持 `D → 一个受监督的 E worker` 两层；已完成任务的历史步骤用于追溯，不重新启动 C、D0 或新 E 会话。

## 2026-09-05：保留功能、收敛实现与验收流程

用户已选择 **1A + 2A**：保留已批准的功能、用户可见行为、质量门槛和安全约束，允许合并重复流程与证据格式，并把验证放在实际证据产生之后。本节是 D/E 后续收敛工作的共同执行依据；与下文、E Plan 或旧 D2 契约冲突的**流程要求**以本节为准。原 Spec 的产品能力和安全不变量不因本修订被删除。

### 保留的结果与现有状态

- 保留 A 的授权路由、复合问答和双开关语义，B 的中文 Analyzer，以及 C 的自然名称、主题、剧情与来源支持的媒体绑定能力。
- 保留 E 的结构/分支信息、Atom BM25、Segment Dense、Typed Dense、融合与预算、多剧情比较、continuation、anchor、AnswerScope、Atom citation 和 REST/SSE 一致性。
- 保留来源与产物身份校验、Owner/授权边界、准确的失败/空检索区分、引用闭包和会话提交原子性。
- 真实 embedding/Milvus 仍由 D 在 E 合并后执行；仍检查云端容量，构建后保留至少 12 GiB，Story Segment 不超过 25,000；不得自动激活、覆盖 active collection 或下载媒体。
- C 与 D0 已完成的提交和证据继续有效。E 在现有工作树、现有会话上继续；按用户最新设置，后续执行使用 `gpt-6-astra / xhigh / 普通速度`，不由历史 Plan 的模型或快速模式条款覆盖。恢复前分别核对模型、思考等级和 service tier；不能仅关闭快速模式选项就假定已切换普通速度。
- 收敛起点为 E HEAD `c81d336806cd9f0b3abb32db01054287df14d711` 及已有 11 个未提交文件。已有改动、失败构建和验收证据保留；不得为了拆提交而重置或重放整条历史。

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

D 本轮只读核对确认：冻结 baseline 是 retrieval-only，保留 85 例 RRF 检索/最终上下文和原始 Dense cassette，`generation_calls=0`，不能充作原始 BM25 或回答/端到端耗时基线；190 条等价记录在两阶段均无匹配（每阶段 48 条缺 source ref、47 条来源版本不符）。原字节和匹配规则保持，不重开 D0，不以 candidate 分数自比。后续评分必须按真实来源和适用分母计算，缺少独立输入的指标继续不通过。

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
