# React Bits 导航、媒体动效与 Wiki 内容呈现设计

> 日期：2026-07-11  
> 状态：已完成设计讨论及 2026-07-13 RAG/EVB 只读契约对齐，等待书面规格审核  
> 适用范围：`frontend/react-app/**`、Wiki 专属构建与 API 兼容层、共享媒体只读审计  
> React Bits 源码基线：`DavidHDev/react-bits@271b49c3ba1db60686e53c8c9a28b7583d5477d5`

## 1. 背景与目标

当前 React + Vite 前端已经具备三屏主站、问答媒体面板、独立 `/wiki` 页面、三套旧主题、Wiki MySQL API 和共享 MinIO 媒体 URL，但交互仍存在以下问题：

- 主站使用 TopNav 与 Sidebar 两套控制面，Wiki 另有 CategoryRail，入口和筛选状态分散。
- 问答语音列表和图片列表只有基础滚动，没有统一的视觉反馈和可靠降级。
- Wiki 左侧条目包含过多描述，主阅读区正文主要以长字符串和松散字段输出。
- Wiki 与资料页图片仍存在不一致的容器、边框和悬停行为。
- 旧主题色与已经从重返未来：1999 官网提取出的主题种子不一致。

本设计的目标是：以本地适配的 React Bits 组件建立统一动效层；以路由感知 Card Nav 替代 Sidebar、TopNav 旧结构和 Wiki CategoryRail；以结构化 `content.blocks` 改造 Wiki 正文；并将官网配色种子接入主站与 Wiki 的同一主题系统。

## 2. 设计原则与非目标

### 2.1 设计原则

1. 动效是展示层增强，不能改变 RAG、Wiki API 或媒体分页语义。
2. 所有动效必须有可读、可操作、不会空白的降级路径。
3. Wiki 继续与 RAG 检索链路解耦；Wiki 构建器只读一次捕获并固定的 active build snapshot，只写 Wiki 自己的 MySQL 表。
4. 媒体以 active activation tuple 指定的 runtime media artifact 和 Wiki MySQL 映射为索引，不扫描 MinIO 对象池反推页面关系。
5. 主题、导航和布局使用共享令牌与共享组件，不为 Wiki 复制一套平行实现。
6. specs 描述架构、契约和优先级；实现步骤与强制验收命令由后续 plan 负责。

### 2.2 非目标

- 不修改 Milvus collection、向量、检索预算、RAG `_state` 或 `/ask` 生成逻辑。
- 不重建 RAG processed artifacts。
- 不实现 Live2D 播放器；保留已有入口和 fallback。
- 不实现 Wiki 后台编辑、版本管理、CDN 或对象删除工具。
- 不将 React Bits 作为运行时远程服务，也不在浏览器运行时从 React Bits 下载代码。

### 2.3 EVB 优先级与并行边界

`2026-07-11-eventname-voice-binding-recovery-design.md`（下称 EVB）是 RAG artifact、active
pointer、Milvus collection、runtime media registry 和共享 MinIO 写入协议的专项权威。
`2026-07-12-minio-blue-green-same-port-migration.md` 是当前 MinIO 镜像、数据目录、同端口切换、
能力证据与未认领上传计划的执行权威。Wiki 任务只能消费已经稳定的公开 API 或固定的只读
artifact snapshot，不得接管 EVB promotion、C20 上传或 MinIO 迁移步骤。

- `COORD-P0-01`：EVB 任务独占 RAG processed artifacts、active pointer、Milvus 和共享 MinIO
  的写权限。Wiki 任务不得修改、替换、重建或提升这些资源。
- `COORD-P0-02`：EVB 执行期间，Wiki 任务只可并行开发 React Bits 适配组件、导航、主题、布局、
  renderer、DOM/WebGL fallback 及基于 fixture/冻结 API contract 的自动化测试。
- `COORD-P0-03`：Wiki MySQL 真实导入、真实媒体映射、`/ask`/SSE/语音分页集成验收和完整浏览器
  E2E 必须在不存在未终态 EVB transaction 时执行，并固定单一 artifact snapshot。有效 active
  pointer 存在时固定完整 activation tuple；pointer 尚不存在时只能使用 `COORD-P0-06` 定义的
  legacy snapshot receipt。
- `COORD-P0-04`：Wiki 后续 plan 必须把并行步骤和 EVB 后置步骤分开；不得用“本任务未主动写入”
  掩盖验收期间由另一任务造成的 pointer、collection 或 artifact 变化。
- `COORD-P0-05`：若 EVB spec 与本文件在 artifact 版本、active build 选择、MinIO 条件创建、
  冲突停止范围、Milvus 或 runtime media registry 上不一致，以 EVB spec 为准。本文件只拥有导航、
  主题、Wiki 展示结构和前端媒体表现的设计权威。
- `COORD-P0-06`：若 `data/processed/huiji/active_build.v1.json` 不存在，Wiki 导入器可以读取
  `config.huiji.build_version` 指定的 configured legacy build，但必须先校验该目录的
  `build_manifest.json`，并对 parent、child、legacy media 三个输入生成 create-new、不可变的
  `wiki_import_snapshot.v1.json` 路径/大小/SHA-256 receipt。该 receipt 只授权本次 Wiki 只读导入，
  不是 RAG active pointer、promotion evidence 或 MinIO 写入授权。
- `COORD-P0-07`：若 active pointer 在 legacy snapshot 导入后出现，或已固定的 activation tuple
  发生变化，已有 Wiki MySQL 数据仍是可追踪的旧快照，但本轮真实集成验收必须标记 stale；重新导入
  和验收前不得宣称 Wiki 与当前 RAG activation 对齐。

2026-07-13 只读审查基线：当前 `active_build.v1.json` 不存在，configured build 仍为 `dev`；
`dev/build_manifest.json` 及 parent/child/media artifacts 存在。MinIO 已运行
`RELEASE.2025-09-07T16-13-09Z`，对外端口仍为 `9002/9003`。RAG 已生成包含 3038 个 voice
`conditional_create` 的未认领 operation plan，C20 upload 未获本任务授权。上述数值和状态只用于
本次审查取证，不能写成未来测试常量。RAG 迁移计划还观察到一批 non-voice 行缺少声明的
`content_sha256`；该缺口不能伪装成 hash conflict，也不能授权上传，Wiki 审计必须按
`MEDIA-P0-11` 单独报告。

### 2.4 2026-07-13 RAG 契约对照结果

| RAG/存储契约 | 原 Wiki 风险 | 本文件的收束结果 |
|---|---|---|
| active pointer + v1 legacy/v2 runtime artifact | 固定读取 `dev/media_assets.jsonl` | `COORD-P0-03`、`COORD-P0-06`、`WIKI-CONTENT-P0-12` 至 `P0-14` 固定单一 snapshot 并记录来源 |
| voice language 由 exact artifact 显式提供 | 前端可能沿用文件名推断或漏掉 `zh-hant` | `VOICE-UI-P0-09` 禁止推断并显式支持 `zh-hant` |
| cursor 绑定 build version 与 activation epoch | 只处理 build mismatch | `VOICE-UI-P0-06`、`P0-10` 区分 400 与 409，并在 409 丢弃旧 cursor |
| 公开媒体只允许安全字段和 HTTP(S) URL | 浏览器或 Wiki API 可能依赖 object key/internal 字段 | `VOICE-UI-P0-11`、`IMAGE-UI-P0-10`、`MEDIA-P0-10` 禁止内部字段进入公开链路 |
| MinIO 只允许可证明的原子条件创建 | 普通 PUT 或 HEAD 后 PUT 存在并发覆盖窗口 | `MEDIA-P0-02` 至 `P0-08` 规定 Wiki 零写入，只能移交 EVB strict uploader |
| MinIO 蓝绿迁移保持 `9002/9003`，C20 独立批准 | 前端可能绑定旧镜像/数据目录，或误认领上传计划 | `IMAGE-UI-P0-10`、`MEDIA-P0-09` 令存储实现对前端透明并禁止 Wiki 执行 C20 |

## 3. 总体架构

```text
App route
├── /                       MainApp
│   ├── RouteAwareCardNav   页面跳转、主题、WIKI 入口
│   ├── HomeSection
│   ├── DataSection         TiltedMedia
│   └── ChatSection
│       ├── AnimatedVoiceList
│       └── CircularMediaGallery
└── /wiki/**                WikiShell
    ├── RouteAwareCardNav   分类筛选、当前页锚点、首页入口、主题
    └── WikiThreePaneLayout
        ├── PageIndex       图片 + 名称，AnimatedContent
        ├── WikiReader      StructuredContentRenderer
        └── PageInfo

active_build.v1.json OR configured legacy build
    -> capture one immutable activation tuple or legacy snapshot receipt
    -> pinned parent/child/runtime media artifact snapshot
    -> Wiki content block builder
    -> Wiki MySQL content_json.blocks
    -> /api/wiki/pages/*
    -> StructuredContentRenderer

active runtime media artifact + Wiki media links
    -> HTTP MinIO URL
    -> DOM image / WebGL texture
    -> deterministic fallback
```

依赖策略：

- 保留现有 `framer-motion`，不再安装 React Bits 示例使用的 `motion`。
- 新增 `gsap`，供 Card Nav、Scroll Reveal 和 Animated Content 使用。
- 新增 `ogl`，供 Circular Gallery 使用。
- 新增 `lucide-react`，供导航、主题、播放和状态图标使用。
- 不安装 `react-icons`；React Bits Card Nav 示例中的图标改为 Lucide。
- 本地适配组件统一位于 `frontend/react-app/src/components/animations/reactbits/`。
- 业务包装组件位于各业务模块附近，业务代码不直接依赖 React Bits 示例的数据模型。

## 4. React Bits 适配层模块

### 4.1 模块职责

React Bits 适配层保存指定效果的核心算法和视觉参数，同时消除示例代码中的全局事件、固定尺寸、全局清理和业务数据耦合。每个适配组件必须暴露项目自己的稳定接口。

指定来源：

- Animated List：<https://reactbits.dev/components/animated-list>
- Circular Gallery：<https://reactbits.dev/components/circular-gallery?bend=0&borderRadius=0.1>
- Card Nav：<https://reactbits.dev/components/card-nav>
- Scroll Reveal：<https://reactbits.dev/text-animations/scroll-reveal?baseRotation=0>
- Animated Content：<https://reactbits.dev/animations/animated-content?direction=horizontal>
- Tilted Card：<https://reactbits.dev/components/tilted-card?displayOverlayContent=false&showTooltip=false&scaleOnHover=1.35&rotateAmplitude=16>

### 4.2 P0 当前必须满足

- `MOTION-P0-01`：适配组件必须使用项目 CSS 变量，不能保留 React Bits 示例中的硬编码黑底、白字或紫色遮罩。
- `MOTION-P0-02`：所有组件必须响应 `prefers-reduced-motion`，降级后内容和控件仍完整可用。
- `MOTION-P0-03`：GSAP 组件只能清理自己创建的 timeline 和 ScrollTrigger，禁止全局杀死其他 trigger。
- `MOTION-P0-04`：列表键盘监听必须绑定到获得焦点的局部容器，禁止监听全局 `window.keydown` 后拦截整页方向键和 Tab。
- `MOTION-P0-05`：固定演示尺寸必须改为由父容器和响应式约束控制，动态内容不能改变导航、媒体区或三栏布局的基本尺寸。
- `MOTION-P0-06`：React Bits 来源、源码提交和本地差异必须留在组件文件头或邻近说明文档中，便于后续升级审计。

### 4.3 P1 可部分支持

- `MOTION-P1-01`：为统一动效包装层增加开发预览页，独立调试主题和 reduced-motion。
- `MOTION-P1-02`：按真实设备性能自动降低动画采样率或禁用模糊。

### 4.4 P2 未来演进

- `MOTION-P2-01`：建立独立视觉回归基线服务和跨浏览器截图矩阵。
- `MOTION-P2-02`：统一更多 React Bits 动效为可配置的页面类型 profile。

### 4.5 关键限制

- 不直接运行 React Bits CLI 覆盖现有组件。
- 不同时维护 `motion` 与 `framer-motion` 两套动画运行时。
- 动效失败不得阻止业务组件渲染。

## 5. 全局 Card Nav 与主题模块

### 5.1 模块职责

`RouteAwareCardNav` 是主站和 Wiki 唯一的全局控制面。它根据当前路由切换一级入口、展开卡片和页面动作，并承载主题切换。旧 Sidebar 和 Wiki CategoryRail 在功能迁移完成后移除。

### 5.2 P0 当前必须满足

- `NAV-P0-01`：主站一级入口显示 `WIKI`，点击进入 `/wiki`；Wiki 一级入口显示 `首页`，点击回到 `/`。
- `NAV-P0-02`：主题图标位于一级入口左侧，始终可见，不依赖展开菜单。
- `NAV-P0-03`：主站展开内容包含“页面”“资料”“项目”三组；页面组定位首页、资料、问答，资料组以当前主站 categories 数据为准，项目组固定为官方网站、数据状态和 Wiki。
- `NAV-P0-04`：Wiki 展开内容包含“浏览”“当前页面”“项目”三组；浏览组动态读取 `/api/wiki/categories`，当前页面组定位正文、媒体、资料锚点，项目组包含首页、问答和官网。
- `NAV-P0-05`：Wiki 分类只有一个状态源。Card Nav 选择分类后直接更新 `WikiShell` 筛选状态，不保留 CategoryRail 的平行状态。
- `NAV-P0-06`：主站页面跳转继续复用现有 scroll-snap 定位，不破坏三屏滚轮结构。
- `NAV-P0-07`：移除 Sidebar、CategoryRail 及其页面占位；旧入口全部迁移后才删除对应 store 状态和测试。
- `NAV-P0-08`：移动端展开内容纵向排列，菜单、主题和一级入口均可用；展开层不遮挡无法关闭的内容。
- `NAV-P0-09`：菜单支持鼠标、触控和键盘，具有正确的 `aria-expanded`、可见焦点和 Escape 关闭行为。
- `NAV-P0-10`：主站项目组固定为“官方网站、数据状态、Wiki”；Wiki 项目组固定为“首页、问答、官方网站”。不存在的当前页锚点显示禁用态，不能跳向空位置。

### 5.3 P1 可部分支持

- `NAV-P1-01`：根据当前 Wiki 页面类型调整展开卡片的强调色和排序。
- `NAV-P1-02`：记录最近访问的 Wiki 页面并显示快捷入口。

### 5.4 P2 未来演进

- `NAV-P2-01`：加入面包屑历史和跨页面过渡编排。
- `NAV-P2-02`：允许用户自定义展开卡片内容。

### 5.5 主题契约

三套主题替换为：

| 主题 | 图标语义 | 背景 | 抬升面 | 主文字 | 次文字 | 主强调 | 次强调 | 边框 |
|---|---|---|---|---|---|---|---|---|
| `storm-dark` | 月亮 | `#080d0d` | `#121716` | `#d8d1bf` | `#9f927b` | `#c06a24` | `#d19643` | `#2e342f` |
| `manuscript-gold` | 太阳 | `#18130d` | `#241b12` | `#e2d5bb` | `#b59b72` | `#d88a2a` | `#f0bc64` | `#4b3521` |
| `cold-archive` | 半日半月 | `#071011` | `#101b1c` | `#cdd8d3` | `#8da09a` | `#b96827` | `#6f8f8a` | `#263a3a` |

- `THEME-P0-01`：主站、Wiki、Card Nav、GSAP 遮罩和 WebGL 标题使用同一组语义令牌。
- `THEME-P0-02`：旧持久化值按 `dark-warm -> storm-dark`、`parchment -> manuscript-gold`、`mystic-purple -> cold-archive` 迁移。
- `THEME-P0-03`：未知持久化值回落到 `storm-dark`，不能产生无 CSS 变量状态。
- `THEME-P0-04`：主题切换保持现有全局背景；首页视频加载完成后仍按既有规则覆盖背景。
- `THEME-P0-05`：主题图标使用 Sun、Moon 和 SunMoon 或等价 Lucide 图标，按钮具有主题名称 tooltip 和可访问标签。

## 6. 问答语音 Animated List 模块

### 6.1 模块职责

语音动效只替换 `VoicePanel` 的列表呈现，不改变台词分组、语言选择、播放器协调器、游标分页或后端媒体契约。

### 6.2 P0 当前必须满足

- `VOICE-UI-P0-01`：一条 `voice_line_id` 对应一个 Animated List 行，语言变体仍位于同一行。
- `VOICE-UI-P0-02`：列表隐藏原生滚动条，但保留滚轮、触控、方向键和 Tab 操作。
- `VOICE-UI-P0-03`：列表顶部和底部渐隐遮罩使用主题令牌，并根据实际滚动位置显示或隐藏。
- `VOICE-UI-P0-04`：加载下一页时仅新增行进场，已加载行、语言选择和去重状态不能重置。
- `VOICE-UI-P0-05`：语言切换、播放另一行、分页请求和卸载继续停止或重置现有音频，任意时刻最多一个音频播放。
- `VOICE-UI-P0-06`：普通分页错误保留已加载行及本地重试；build version 或 activation epoch
  失效返回 HTTP 409 时停止当前音频、丢弃旧 cursor，并提供首屏重载动作，不能自动重放旧 cursor。
- `VOICE-UI-P0-07`：列表高度使用响应式上限，不让消息气泡随语音总量无限增长。
- `VOICE-UI-P0-08`：reduced-motion 下取消缩放和淡入时序，但列表、分页和播放功能完整。
- `VOICE-UI-P0-09`：语言只能读取后端 voice variant 的显式 canonical language；支持顺序为
  `zh`、`zh-hant`、`en`、`jp`、`kr`、其余显式语言。不得从 eventName、filename、audio ID、
  title、URL 或 object key 推断语言，`zh-hant` 不得借用 `zh` URL。
- `VOICE-UI-P0-10`：非法或未知 cursor 的 HTTP 400 只显示本地重试/错误；HTTP 409 必须走首屏
  重载分支。两个状态不能合并为同一种无限重试行为。
- `VOICE-UI-P0-11`：前端只消费公开 voice page 字段并容忍公开契约的新增可选字段；任何响应中
  出现 `object_key`、hash、`source_url`、`local_relpath`、完整 quality flags 或本地路径均为红灯。

### 6.3 P1 可部分支持

- `VOICE-UI-P1-01`：当前播放行可显示轻量进度反馈。
- `VOICE-UI-P1-02`：记忆同一角色在当前会话中的首选语言。

### 6.4 P2 未来演进

- `VOICE-UI-P2-01`：语音波形和逐句字幕同步。

### 6.5 不变契约

- 不修改 `GET /api/media/voice/page`。
- 不增加 entity、offset 或 page-size 客户端参数。
- 不把完整语音列表重新塞回首个 Ask/SSE 响应。

## 7. 问答图片 Circular Gallery 模块

### 7.1 模块职责

图片面板使用 OGL Circular Gallery 展示现有 Ask/SSE 图片媒体，并在任何 WebGL 或纹理失败场景下提供同数据源的 DOM 横向列表。

### 7.2 P0 当前必须满足

- `IMAGE-UI-P0-01`：画廊参数固定为 `bend={0}` 和 `borderRadius={0.1}`。
- `IMAGE-UI-P0-02`：支持横向拖拽、滚轮和触控，不显示原生滚动条。
- `IMAGE-UI-P0-03`：画廊条目由现有 `MediaItem.url/title/alt` 生成，不改变 RAG 响应模型。
- `IMAGE-UI-P0-04`：OGL 动态导入，仅在回答中存在图片媒体时加载。
- `IMAGE-UI-P0-05`：容器使用稳定响应式高度和宽度，Canvas、纹理和标题加载不能改变消息布局。
- `IMAGE-UI-P0-06`：WebGL 初始化失败、上下文丢失、纹理失败、零尺寸容器或 reduced-motion 均切换为无滚动条 DOM 图片带。
- `IMAGE-UI-P0-07`：单张图片失败只影响该条目；其余图片和 fallback 继续可用。
- `IMAGE-UI-P0-08`：Canvas 外保留图片名称、当前项状态和键盘可达的等价操作，不能形成只可鼠标操作的黑盒。
- `IMAGE-UI-P0-09`：必须使用至少一条真实 MinIO 图片 URL 验证 Canvas 非空和可滑动，mock 图片通过不代表完成。
- `IMAGE-UI-P0-10`：浏览器只消费 API 返回的安全 HTTP(S) `url`，不得拼接 MinIO endpoint、bucket、
  prefix 或 object key。MinIO 镜像、容器数据目录或凭据变化不能要求修改前端媒体代码。

### 7.3 P1 可部分支持

- `IMAGE-UI-P1-01`：点击当前图片打开同源大图查看层。
- `IMAGE-UI-P1-02`：对大量图片进行纹理窗口化和预加载预算控制。

### 7.4 P2 未来演进

- `IMAGE-UI-P2-01`：图片与答案引用片段双向定位。

### 7.5 真实媒体前提

2026-07-11 曾抽样验证 MinIO 图片 URL 对 `http://localhost:5173` 和
`http://127.0.0.1:5173` 返回匹配的 `Access-Control-Allow-Origin`。2026-07-13 MinIO 已完成
同端口蓝绿升级，因此后续验收必须针对当前 `RELEASE.2025-09-07T16-13-09Z` 实例重新验证 URL、
字节、CORS 与 WebGL texture 读取；旧实例抽样不能作为永久配置保证。

## 8. Wiki 导航与三栏布局模块

### 8.1 模块职责

Wiki 页面取消 CategoryRail，只保留条目列表、主阅读区和右信息栏三个可见结构。分类筛选进入 Card Nav。

### 8.2 P0 当前必须满足

- `WIKI-LAYOUT-P0-01`：桌面布局只有 `PageIndex / WikiReader / PageInfo` 三栏，比例满足 `PageInfo < PageIndex < WikiReader`。
- `WIKI-LAYOUT-P0-02`：页面不存在 CategoryRail 热区、隐藏宽度或预留列。
- `WIKI-LAYOUT-P0-03`：PageIndex 条目只显示图片和名称，不显示大段摘要、类型说明或来源描述。
- `WIKI-LAYOUT-P0-04`：PageIndex 使用 `AnimatedContent direction="horizontal"`；分类变化时新列表进场，单页选择不重播整列。
- `WIKI-LAYOUT-P0-05`：条目图片加载前保留稳定比例；角色优先使用角色缩略图，其他类型使用相应封面或固定主题占位。
- `WIKI-LAYOUT-P0-06`：页面支持全局纵向滚动；PageIndex 和 PageInfo 在需要时可局部滚动且不显示原生滚动条。
- `WIKI-LAYOUT-P0-07`：窄屏按 `PageIndex -> WikiReader -> PageInfo` 排列，不使用固定像素总宽度，不产生水平溢出。
- `WIKI-LAYOUT-P0-08`：Card Nav 分类状态、PageIndex 查询和当前页面选择组合后仍只有一个明确的请求参数集合。

### 8.3 P1 可部分支持

- `WIKI-LAYOUT-P1-01`：不同页面类型使用不同列表进场距离、节奏和强调色，但共享同一 AnimatedContent 包装层。
- `WIKI-LAYOUT-P1-02`：移动端将 PageIndex 切换为可收起的顶部抽屉。

### 8.4 P2 未来演进

- `WIKI-LAYOUT-P2-01`：跨 Wiki 页面共享元素过渡。
- `WIKI-LAYOUT-P2-02`：用户可调整三栏比例并持久化。

## 9. Wiki 结构化内容模块

### 9.1 模块职责

Wiki 内容构建器把一次捕获并固定的 active build snapshot 中的页面、子块和媒体引用转换成稳定的展示区块；前端只负责按区块类型渲染和动效，不在组件内猜测整页业务结构。导入开始后不得跟随 active pointer 热切换输入版本。

### 9.2 内容契约

```ts
type WikiContentBlock =
  | { id: string; type: 'heading'; text: string; level: 1 | 2 | 3 }
  | { id: string; type: 'paragraph'; text: string; reveal: boolean }
  | { id: string; type: 'facts'; items: Array<{ label: string; value: string }> }
  | { id: string; type: 'list'; ordered: boolean; items: string[] }
  | { id: string; type: 'quote'; text: string }
  | { id: string; type: 'table'; headers: string[]; rows: string[][] }
  | { id: string; type: 'media'; mediaIds: string[] }
  | { id: string; type: 'voice'; sectionKey: string }
```

`content_json` 保留现有字段，并新增：

```json
{
  "contentVersion": 1,
  "blocks": []
}
```

### 9.3 P0 当前必须满足

- `WIKI-CONTENT-P0-01`：API 继续返回 `content` 对象；新增 `contentVersion/blocks` 不破坏旧客户端。
- `WIKI-CONTENT-P0-02`：角色现有 `sections/skills` 转换为 blocks，并按 `sectionKey` 分组；语音不混入普通长正文。
- `WIKI-CONTENT-P0-03`：story、item、psychube 页面优先根据 pinned build 的 `child_blocks.jsonl` 中 `title/text/section_kind/media_ids` 构建 blocks。
- `WIKI-CONTENT-P0-04`：`字段名: 值` 与 `字段名：值` 转换为 facts；Markdown 标题、列表、引用和表格转换为对应语义块。
- `WIKI-CONTENT-P0-05`：可解析 JSON 转换为键值、列表和嵌套分区，不在页面中展示整串原始 JSON。
- `WIKI-CONTENT-P0-06`：只有缺少结构标记且超过 240 个 Unicode code point 的段落才按原始换行优先、中文 `。！？` 和英文 `.?!` 次之进行兜底分段；短段落中的句号不能产生新区块。
- `WIKI-CONTENT-P0-07`：每个 block ID 从页面 ID、section key、child ID 或稳定序号确定，同一构建输入必须得到同一顺序和 ID。
- `WIKI-CONTENT-P0-08`：前端优先渲染 blocks；旧数据缺少 blocks 时使用兼容转换器；转换失败至少显示安全摘要，不能显示空白页。
- `WIKI-CONTENT-P0-09`：构建过程只更新 Wiki MySQL 自有表，不修改 parent/child/media JSONL、Milvus 或 RAG 状态。
- `WIKI-CONTENT-P0-10`：必须以真实 character、story、item、psychube 页面各至少一页验收；当前总数或特定页面 ID不能写死为算法条件。
- `WIKI-CONTENT-P0-11`：JSON 展开最多递归三层；空字符串、空数组和空对象不生成展示行，数值 `0` 与布尔值必须保留。超过三层的对象作为可折叠详情块保存，不能丢弃原数据。
- `WIKI-CONTENT-P0-12`：导入器必须在启动时执行一次 snapshot resolve。active pointer 存在时校验
  activation tuple、build manifest 和 artifact schema 后固定输入路径；pointer 不存在时仅允许
  `COORD-P0-06` 的 legacy snapshot receipt。导入报告必须记录 source mode、activation ID（可空）、
  generation（可空）、build version、artifact schema version、manifest SHA-256 和三个输入 SHA-256。
  导入期间 pointer 或 configured build 变化不得混入新版本，但必须使本轮验收标记为 stale。
- `WIKI-CONTENT-P0-13`：generation 0 只可通过 EVB 定义的 v1 legacy adapter 读取 configured dev；
  v2 generation 只可读取 active build 的 `runtime/media_assets.v2.jsonl`。不得把 legacy
  `media_assets.jsonl` 与 v2 行合并为同一次 Wiki 导入输入。
- `WIKI-CONTENT-P0-14`：Wiki MySQL 必须保存最近一次成功导入的 snapshot metadata；
  `/api/wiki/health` 只公开 `sourceMode`、`buildVersion`、`artifactSchemaVersion`、可空
  `activationEpoch`、manifest SHA-256 前 12 位和 `stale`，不得公开绝对路径、object key、凭据或
  完整内部 activation transaction。

### 9.4 P1 可部分支持

- `WIKI-CONTENT-P1-01`：为不同 `section_kind` 增加专用 facts/table 映射。
- `WIKI-CONTENT-P1-02`：将 link spans 应用到 block 内关键词，点击跳转目标 Wiki route。
- `WIKI-CONTENT-P1-03`：为构建失败或低质量 blocks 输出可审计报告。

### 9.5 P2 未来演进

- `WIKI-CONTENT-P2-01`：基于 schema 的页面模板编辑与预览。
- `WIKI-CONTENT-P2-02`：关系图谱、时间线和复杂剧情交互块。

### 9.6 观察到的基线

2026-07-11 当前项目 MySQL 抽样为：Wiki 页面 7456，包含 character 132、story 6413、item 906、psychube 5。该数字用于说明真实数据面，不作为未来验收固定值。角色已含 `sections/skills`，其他类型主要为 `summary/childCount/sourceRefs/sectionKind`，因此 blocks 必须由 Wiki 构建层补齐，而不能只在前端按句号拆分。

## 10. Wiki Scroll Reveal 模块

### 10.1 模块职责

Scroll Reveal 只增强适合滚动阅读的短文本，不接管所有 Wiki 文本。

### 10.2 P0 当前必须满足

- `WIKI-TEXT-P0-01`：固定 `baseRotation={0}`。
- `WIKI-TEXT-P0-02`：标题、摘要和短 paragraph 使用逐词透明度与模糊揭示。
- `WIKI-TEXT-P0-03`：facts、表格、列表控件、语音、按钮和长 paragraph 不逐词拆分。
- `WIKI-TEXT-P0-04`：ScrollTrigger 使用真实 Wiki 滚动容器；页面选择或卸载后只清理自身 trigger。
- `WIKI-TEXT-P0-05`：动态切换页面后刷新测量，不能继续引用前一页面的词节点。
- `WIKI-TEXT-P0-06`：reduced-motion 下文本立即完整显示。
- `WIKI-TEXT-P0-07`：短 paragraph 定义为不超过 180 个 Unicode code point 且不包含表格或代码语法；超过该上限时 `reveal=false`。

### 10.3 P1 可部分支持

- `WIKI-TEXT-P1-01`：不同页面类型使用不同揭示距离和模糊强度。

### 10.4 P2 未来演进

- `WIKI-TEXT-P2-01`：阅读进度与目录高亮联动。

## 11. Wiki 与资料页 Tilted Media 模块

### 11.1 模块职责

统一 Wiki 主阅读区和主站资料页图片的透明媒体舞台和指针倾斜行为。

### 11.2 P0 当前必须满足

- `TILT-P0-01`：桌面 hover 设备使用 `scaleOnHover={1.35}` 和 `rotateAmplitude={16}`。
- `TILT-P0-02`：`displayOverlayContent={false}`、`showTooltip={false}`。
- `TILT-P0-03`：图片及舞台背景透明，不显示装饰外框、卡片背景或阴影。
- `TILT-P0-04`：媒体舞台预留放大空间并隔离层叠上下文，放大图片不能不合理遮挡正文、导航或邻近图片。
- `TILT-P0-05`：图片保持 `object-fit: contain`，不裁掉角色立绘和心相主体。
- `TILT-P0-06`：触控和 reduced-motion 下禁用倾斜与 hover 放大，保持原尺寸完整显示。
- `TILT-P0-07`：角色立绘与 Live2D fallback 继续共用一个媒体窗口和切换入口。

### 11.3 P1 可部分支持

- `TILT-P1-01`：多图页面支持焦点图切换并保持同一舞台尺寸。

### 11.4 P2 未来演进

- `TILT-P2-01`：Live2D 播放器就绪后在同一媒体窗口加载真实模型。

## 12. 共享媒体完整性与 EVB 修复移交模块

### 12.1 模块职责

Wiki 任务只验证真实展示资产是否存在，不拥有独立的共享 MinIO uploader。缺失对象阻塞 P0 视觉
验收时，必须生成可审计修复请求并移交 EVB strict uploader；上传、冲突闭包和 promotion 仍由
EVB 协议控制。

### 12.2 P0 当前必须满足

- `MEDIA-P0-01`：以 `WIKI-CONTENT-P0-12` 固定的 active runtime media artifact 为索引，逐项
  验证计划使用的安全 HTTP(S) `url`；内部审计可使用 artifact 中已验证的 object identity，但不
  扫描对象池反推关系，也不把 `object_key` 暴露给浏览器。
- `MEDIA-P0-02`：Wiki 任务对共享 MinIO 始终零写入；对象均存在时只输出只读验收报告。
- `MEDIA-P0-03`：若对象缺失且阻塞真实页面验收，Wiki 任务只生成
  `wiki_media_repair_request.v1.json`，记录 pinned activation/build、稳定 media ID、期望对象身份、
  缺失证据和来源 provenance；不得自行从本地文件或 source URL 上传。
- `MEDIA-P0-04`：修复请求只能交给 EVB `EVB-STORE-P0-01` 至 `EVB-STORE-P0-09` 的 strict
  uploader。禁止普通 PUT、先 HEAD 后 PUT、overwrite retry 或客户端锁；缺失对象只允许服务端
  `If-None-Match: *` 等价的原子条件创建。
- `MEDIA-P0-05`：发现同 key 内容冲突、条件创建竞争、来源 hash 不一致或 capability 不可证明时，
  必须停止本批次后续写入和 promotion，并由 EVB 扩大只读诊断范围；不得仅跳过单对象后继续上传。
- `MEDIA-P0-06`：禁止删除对象、清空 bucket/prefix、重命名共享对象、修改 bucket 配置或修改
  RAG media manifest。
- `MEDIA-P0-07`：Wiki 报告必须区分 `verified`、`missing`、`repair-requested`、`conflict`、
  `blocked-by-evb` 和 `stale-activation`，且不得包含凭据、本地绝对路径或公开 payload 禁止字段。
- `MEDIA-P0-08`：EVB 未到终态、存在未终态 activation transaction、pinned activation 已变化，
  或 shared storage capability/audit 证据不足时，Wiki 真实媒体验收和任何修复请求执行必须阻断。
- `MEDIA-P0-09`：当前 RAG/EVB missing-voice operation plan 属于 RAG/EVB，且保持未认领；Wiki 任务
  不得 claim、执行 C20、复制为新计划或把它作为图片/Wiki 媒体修复计划。任何共享对象写入都需要
  用户对精确 hash-pinned operation plan 的独立批准。
- `MEDIA-P0-10`：MinIO 迁移后仍通过 API URL 保持对前端透明；Wiki 前端和公开 API 不读取
  `MINIO_ROOT_USER`、`MINIO_ROOT_PASSWORD`、内部 service endpoint 或 cutover volume path。
- `MEDIA-P0-11`：non-voice artifact 缺少 `content_sha256` 时，按 `unverified-content-sha256`
  单独报告；已有 SHA-1、size、HTTP readback、mime 和浏览器 decode 仍可用于只读展示验收，但该行
  不能据此分类为 `same_hash`、conflict 或 upload-eligible，也不能借用其他对象的 SHA-256。

### 12.3 P1 可部分支持

- `MEDIA-P1-01`：将完整 manifest 存在性审计加入只读运维命令。
- `MEDIA-P1-02`：为图片生成独立缩略图对象和显式映射，不覆盖原图。

### 12.4 P2 未来演进

- `MEDIA-P2-01`：CDN、生命周期策略和媒体管理后台。

## 13. 响应式、可访问性与性能模块

### 13.1 P0 当前必须满足

- `QUALITY-P0-01`：桌面、窄桌面和移动端均不得出现导航、文字、图片、列表和 PageInfo 的不合理重叠。
- `QUALITY-P0-02`：固定格式区域必须使用 `minmax`、`clamp`、`aspect-ratio` 或稳定高度，不能按视口宽度直接缩放字体。
- `QUALITY-P0-03`：隐藏滚动条不能移除滚动能力和键盘焦点；可滚动区域具有可访问名称或明确上下文。
- `QUALITY-P0-04`：所有图标按钮具有 tooltip 或 `aria-label`，熟悉图标不重复显示功能说明文本。
- `QUALITY-P0-05`：Canvas 必须通过像素检查证明非空，并提供 DOM 可访问等价内容。
- `QUALITY-P0-06`：OGL 只在图片面板存在时加载；首屏和无图片回答不下载画廊运行时代码。
- `QUALITY-P0-07`：远程图片保留懒加载；首张 Wiki 主图可提高优先级但不得一次预加载整页媒体。
- `QUALITY-P0-08`：三个主题下正文、按钮、选中态和焦点态均清晰可辨。

### 13.2 P1 可部分支持

- `QUALITY-P1-01`：记录动画初始化耗时、WebGL fallback 原因和图片失败计数，仅用于本地诊断。

### 13.3 P2 未来演进

- `QUALITY-P2-01`：真实设备性能分档和资源预算面板。

## 14. 数据流与错误处理

### 14.1 问答媒体数据流

```text
Ask/SSE Message.media + Message.mediaPanels
    -> MessageAssets 去重与分型
    -> VoicePanel / ImagePanel
    -> AnimatedVoiceList / CircularMediaGallery
    -> functional DOM fallback
```

任何动画失败都停留在最后两层，不能向上改变 Message、SSE 或 store 契约。

### 14.2 Wiki 数据流

```text
active pointer + pinned build manifest OR legacy snapshot receipt
    -> pinned parent_blocks + child_blocks + one schema-compatible media artifact
    -> Wiki block builder
    -> Wiki MySQL content_json.blocks + wiki_media_links
    -> /api/wiki/pages/*
    -> WikiTemplate
    -> StructuredContentRenderer
```

兼容顺序：

1. 有效 `contentVersion=1` 和 blocks。
2. 旧角色 `sections/skills` 转换。
3. 旧 summary/content 的安全兼容解析。
4. 安全摘要 fallback。

### 14.3 错误处理原则

- Card Nav 分类加载失败时保留静态页面入口和主题按钮。
- Wiki 分类失败不阻止已知 route 页面加载。
- 单个 block 异常跳过该 block 并保留页面标题与摘要。
- 单张媒体失败不删除其他媒体。
- WebGL 失败立即使用 DOM fallback，不循环重启 Canvas。
- 共享媒体冲突停止本批次后续写入和 promotion，生成修复请求与扩大诊断报告；Wiki 任务不自动上传或覆盖。

## 15. 测试与验收方向

后续 plan 必须把本节每个 P0 编号转换为“实现位置 + 测试位置 + 命令 + 真实数据验收 + 失败表现”。只通过单元测试不能宣称完成。

### 15.1 自动化测试方向

- Card Nav 路由切换、菜单内容、主题图标、Escape/键盘、Sidebar/CategoryRail 移除。
- 主题旧值迁移、未知值 fallback 和三主题 CSS 令牌完整性。
- Animated List 新增行动画、局部键盘、隐藏滚动条和语音状态不回归。
- Circular Gallery 动态导入、WebGL fallback、上下文丢失、图片失败和无图片不加载。
- blocks 构建器的角色 sections、facts、Markdown、JSON、长段落和稳定 ID。
- StructuredContentRenderer 对全部 block 类型和旧数据 fallback 的渲染。
- ScrollReveal 的局部 trigger 清理和 reduced-motion。
- Tilted Media 指定参数、透明舞台、触控降级。
- active pointer capture、v1/v2 adapter、pinned snapshot 和导入期间 pointer 变化使用 fixture 验证。
- pointer 缺失时 legacy snapshot receipt 的 create-new、输入 SHA-256、stale 判定和 health 脱敏字段。
- voice variant 显式语言、`zh-hant`、400/409 分流、activation epoch 失效和禁止文件名推断。
- 共享媒体只读审计与修复移交使用 fake client 验证 Wiki 零写入、修复请求 schema、禁止普通 PUT、
  strict conditional-create 委托和冲突后停止批次。

### 15.2 真实数据验收方向

- 确认不存在未终态 EVB transaction 后，固定 active activation tuple；若 pointer 尚不存在，则固定
  hash-pinned legacy snapshot receipt。使用该单一 snapshot 导入的 MySQL + `/api/wiki` 打开
  character、story、item、psychube 各至少一页。
- 使用当前 MinIO HTTP URL 在问答图片 Gallery 和 Wiki 主图各显示至少一张真实图片。
- 使用存在多页语音的真实角色验证分页追加、语言切换和单音频播放。
- 在 Chromium 桌面、窄桌面和移动视口验证 Card Nav、Wiki 三栏/纵向布局和图片放大空间。
- 对 Circular Gallery 执行 Canvas 非空像素检查、拖动前后画面变化检查和强制 WebGL 失败 fallback。
- 验收前固定 EVB active activation tuple 或 legacy snapshot receipt；Wiki 验收窗口内 Milvus
  collection、generation、build manifest 和 media manifest 必须保持不变。若外部任务改变它们，
  本轮标记 stale 并重新验收，不得把变化归因于 Wiki 或接受混合版本结果。
- 若产生共享媒体修复请求，核对 Wiki 零写入证据和 EVB strict uploader 报告；修复完成后必须固定
  新的终态 activation snapshot 并重新运行真实数据验收。

### 15.3 完成判定

本轮完成必须同时满足：

1. 进入 plan 的全部 P0 条目逐项通过。
2. 前端完整测试和生产构建通过。
3. Wiki/API 相关后端测试通过。
4. `/ask`、SSE 和语音分页 smoke test 通过。
5. 真实 MySQL + MinIO + API + React 浏览器链路通过。
6. 桌面与移动视觉验收无空白、重叠和不可操作区域。
7. Wiki 任务未改变 Milvus、RAG processed artifacts、active pointer 或共享 MinIO；整个验收使用
   单一 pinned activation tuple 或 legacy snapshot receipt，未混入 EVB transaction 变化。

## 16. 与既有规格的关系

- 保留 `2026-07-04-huiji-wiki-frontend-design.md` 中的 Wiki/RAG 解耦、MySQL 展示库、MinIO 共享和 RAG route bridge 边界。
- 保留 `2026-07-10-multi-intent-rag-and-voice-pagination-design.md` 的多意图、语音分组和单播放器契约；
  其中 artifact、cursor build/epoch 和公开字段若与 EVB 不一致，以 EVB 为准。本设计仅替换前端列表表现。
- 遵循 `2026-07-11-eventname-voice-binding-recovery-design.md` 的 active build、v1/v2 artifact、
  runtime registry、MinIO strict uploader、冲突停止、Milvus 和 activation transaction 契约；
  本设计不得覆盖这些专项边界。
- 本设计取代旧前端规格中 Sidebar、旧 TopNav、旧主题名称和“React Bits 动效仅作为未来 P2”的描述。
- 本设计不推翻 `2026-07-08-huiji-wiki-native-8000-mysql-migration-design.md` 的 `/api/wiki/* -> :8000` 和项目 MySQL 归属。
- 遵循 `2026-07-12-minio-blue-green-same-port-migration.md` 已接受的 MinIO 镜像、`9002/9003`
  同端口、对象不变和 C20 独立批准边界；前端不得依赖 cutover 数据目录或内部 service endpoint。
- 若既有文档与本设计在导航、主题、Wiki CategoryRail、问答媒体动效或 Wiki blocks 上冲突，以本设计为准；RAG、active build、存储、Milvus、runtime media registry 和 API 边界以 EVB 及各自专项规格为准。

## 17. 已批准的关键决策

- 采用“本地适配 React Bits + 结构化内容契约”方案。
- Scroll Reveal 使用区块级粒度，不对所有长正文逐词动画。
- Card Nav 成为唯一全局控制面，取消 Sidebar 和 Wiki CategoryRail。
- Wiki PageIndex 仅显示图片和名称。
- Circular Gallery 使用指定参数并保留 DOM fallback。
- Wiki 与资料页图片使用指定 Tilted Card 参数、透明背景和无外框。
- 三套官网配色种子替换旧主题并迁移持久化值。
- Wiki 对共享 MinIO 始终只读；真实对象缺失时只生成修复请求，由 EVB strict uploader 在独占窗口处理。
