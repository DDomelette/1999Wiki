# Kimi Wiki 真实 API 并行预览接入设计

日期：2026-07-17  
状态：已完成方案讨论，等待书面规格审核  
上位视觉规格：`2026-07-13-stitch-archival-wiki-global-redesign.md`

## 1. 背景与目标

`kimi_web` 已形成角色选人页、PC 角色详情页、移动角色选人页和移动角色详情页的高完成度 Stitch 复刻，但其运行时仍是独立 Vite 原型，页面切换、角色内容和媒体注册表不属于正式 Wiki 数据链路。正式前端 `frontend/react-app` 已具备 `/api/wiki/*`、稳定 route、TypeScript DTO、Card Nav、三主题、搜索分页、错误状态和自动化测试。

本轮目标是在不覆盖正式 `/wiki/*` 的前提下，把 `kimi_web` 的视觉组件原生迁入正式 React 应用，建立 `/wiki-preview/*` 并行预览入口，并使用真实项目 MySQL、`:8000/api/wiki/*` 与 API 已映射的 MinIO HTTP URL 驱动页面。预览通过真实数据、交互和视觉验收后，后续任务才允许将其替换为正式 Wiki 页面。

本轮不修改 RAG、Milvus、MySQL 表、MinIO 对象和 Wiki 后端契约。

## 2. 总体架构

```text
Browser
  -> frontend/react-app
     -> /wiki/*                 现有正式 Wiki，保持不变
     -> /wiki-preview/character Kimi 选人预览
     -> /wiki-preview/**        Kimi 详情预览
        -> existing src/api/wiki.ts
        -> Kimi preview ViewModel adapter
        -> native React preview components
           -> RouteAwareCardNav
           -> approved Stitch layout and local assets

frontend/react-app /api/wiki proxy
  -> FastAPI :8000 /api/wiki/*
  -> project MySQL
  -> public HTTP media URLs mapped from shared MinIO
```

预览不是第二套应用、iframe 或微前端。`kimi_web` 只作为视觉与组件实现参考，不参与正式运行时构建。

## 3. 并行预览路由模块

### 3.1 模块职责

在同一个 React 应用内隔离预览和正式 Wiki，支持选人、详情、刷新、浏览器 Back/Forward 和后续无损切换正式入口。

### 3.2 P0 当前必须满足

- `PREVIEW-ROUTE-P0-01`：新增精确 `/wiki-preview/character` 选人入口；正式 `/wiki/character` 与现有深层 `/wiki/**` 行为不得改变。
- `PREVIEW-ROUTE-P0-02`：API 返回的 canonical route 只在浏览器预览地址中把首段 `/wiki` 映射为 `/wiki-preview`。读取详情时再还原 canonical route 并调用 `fetchWikiPageByRoute()`，不得自行猜测唯一的 `char` 或 `character` 命名。
- `PREVIEW-ROUTE-P0-03`：刷新预览详情、浏览器 Back/Forward 和选人页返回状态均可用；路由状态不能只存在于组件局部 `useState`。
- `PREVIEW-ROUTE-P0-04`：预览继续使用 `RouteAwareCardNav`，一级入口、主题状态和可访问交互不得复制第二套实现。

### 3.3 P1 可部分支持

- `PREVIEW-ROUTE-P1-01`：用户批准预览后，将正式 `/wiki/character` 与详情 route 的渲染组件切换到预览组件树，并保留一个短期回退开关。

### 3.4 P2 未来演进

- `PREVIEW-ROUTE-P2-01`：为剧情、心相、世界、阵营和日历建立同等完成度的 Kimi/Stitch 专属页面。

### 3.5 关键契约与限制

预览 route 只属于前端验收层，不能写回 API、MySQL 或 RAG 来源链接。正式替换后仍以 API 返回的 `page.route` 为规范地址。

## 4. Wiki API 适配模块

### 4.1 模块职责

把现有 `WikiCategoryItem`、`WikiPageListItem` 和 `WikiPageDetail` 转换为视觉组件可直接消费、可测试且不包含基础设施细节的预览 ViewModel。

### 4.2 P0 当前必须满足

- `PREVIEW-DATA-P0-01`：分类、角色列表、搜索、分页、详情和 route 解析只能调用现有 `src/api/wiki.ts`；不得读取 `kimi_web/src/data/*.js`。
- `PREVIEW-DATA-P0-02`：建立纯函数 ViewModel 适配层，输出选人条目、身份摘要、初始/洞悉立绘状态、技能、传承、塑造、语音、文化和藏品。视觉组件不得直接遍历任意 `content` JSON 猜字段。
- `PREVIEW-DATA-P0-03`：优先消费 API canonical 内容与 supplement 合并结果；缺少某个 section 时只隐藏对应模块或显示明确不可用状态，不得回退到槲寄生硬编码文本。
- `PREVIEW-DATA-P0-04`：`/api/wiki/health` 的 supplement 状态仅用于预览诊断。`supplementReady=false` 或 `supplementStale=true` 时页面不得白屏，但验收必须标记失败。
- `PREVIEW-DATA-P0-05`：列表累计分页、短词搜索和 CTA route 继续遵守正式 Wiki API 契约，不得在预览层重新实现数据库排序或实体匹配。

### 4.3 P1 可部分支持

- `PREVIEW-DATA-P1-01`：把预览 ViewModel 收敛为正式角色 Wiki 的唯一展示适配层，删除被替代的重复角色适配代码。

### 4.4 P2 未来演进

- `PREVIEW-DATA-P2-01`：为非角色模板建立独立 typed ViewModel，而不是复用角色 schema。

### 4.5 关键契约与限制

API DTO 是唯一运行时输入。前端适配层可以重组展示顺序，但不能修正、补造或持久化业务数据。

## 5. 角色选人预览模块

### 5.1 模块职责

以已批准的 PC 与移动端选人截图为视觉权威，用真实列表数据完成搜索、分页、选中预览和进入详情。

### 5.2 P0 当前必须满足

- `PREVIEW-SELECT-P0-01`：PC 端复刻批准的档案工作台层级，移动端复刻独立滚动选人框与下方全局概述流；不得重新退化为通用卡片网格。
- `PREVIEW-SELECT-P0-02`：条目只显示真实 API 的缩略图、角色名与稳定元数据；图片缺失使用固定尺寸占位，不得使用原型角色图片冒充。
- `PREVIEW-SELECT-P0-03`：搜索输入、分类条件、分页游标、当前选中项和进入详情 CTA 全部连接真实 API。
- `PREVIEW-SELECT-P0-04`：列表加载、空结果、接口失败和重试状态在既定布局内可见，失败不能伪装为 `0 pages`。
- `PREVIEW-SELECT-P0-05`：PC 参考视口、移动参考视口和相邻常见宽度均无横向溢出、文字遮挡和不可达内容。

### 5.3 P1 可部分支持

- `PREVIEW-SELECT-P1-01`：正式替换后保存最近访问和选人滚动位置。

### 5.4 P2 未来演进

- `PREVIEW-SELECT-P2-01`：为不同 Wiki 分类提供独立选取动效和视觉模板。

### 5.5 关键契约与限制

页面内 Dossier/Psychube/Insight/Resonate/Wardrobe 只属于角色工作区，不替代 Card Nav 的全局分类与路由职责。

## 6. 角色详情预览模块

### 6.1 模块职责

以已批准的 PC 详情截图和移动端连续截图为视觉权威，使用同一份真实详情 DTO 驱动两个响应式组件树。

### 6.2 P0 当前必须满足

- `PREVIEW-DETAIL-P0-01`：PC 端保留背景环境、主立绘、左档案轨和右磨砂资料区的固定视觉层级；移动端使用自然长文档流，不对 PC 页面整体缩放。
- `PREVIEW-DETAIL-P0-02`：Initial/Insight/Live2D 共用同一媒体窗口并互斥显示；Live2D 播放器未实现时保留入口和明确不可用状态。
- `PREVIEW-DETAIL-P0-03`：身份资料、三张技能、传承、LV.1-LV.5 塑造、语音、文化与藏品由 ViewModel 实际数据驱动。模块顺序和标题遵守批准截图，数据缺失不得用静态数组填充。
- `PREVIEW-DETAIL-P0-04`：PC 资料区独立滚动与移动端全局滚动均可通过鼠标、触控、键盘和焦点访问全部内容。
- `PREVIEW-DETAIL-P0-05`：角色切换后所有文字、媒体、技能和档案模块同步更新，不保留上一角色的静态内容。

### 6.3 P1 可部分支持

- `PREVIEW-DETAIL-P1-01`：正式替换后接入 RAG 来源到规范 Wiki route 的跳转与目标段落定位。

### 6.4 P2 未来演进

- `PREVIEW-DETAIL-P2-01`：接入真实 Live2D 播放器和更完整的皮肤联动。

### 6.5 关键契约与限制

PC 与移动端可以共享 ViewModel 和基础视觉令牌，但必须使用适合各自信息密度与滚动模型的组件树，不能通过 CSS 缩放伪造响应式页面。

## 7. 媒体与安全模块

### 7.1 模块职责

确保预览实际消费 Wiki API 公开媒体 DTO，同时保持 Docker、MySQL 和 MinIO 内部映射只在后端存在。

### 7.2 P0 当前必须满足

- `PREVIEW-MEDIA-P0-01`：所有页面图片、音频和其他媒体只能来自 `WikiPageDetail.mediaLinks` 或列表 `thumbnail` 的 HTTP(S) URL。
- `PREVIEW-MEDIA-P0-02`：运行时代码和构建产物不得包含 `objectKey`、MinIO 内部 endpoint、bucket 密钥、本地盘符、`file://` 或 `local_relpath`。
- `PREVIEW-MEDIA-P0-03`：删除或隔离 `kimi_web` 的 `WIKI_MEDIA_LINKS`、`BACKEND_ONLY` 和本地 `getPageMedia()` 模拟链路；不得把模拟注册表当作真实接口证明。
- `PREVIEW-MEDIA-P0-04`：媒体检查器若保留，只能在开发环境订阅页面已收到的公开 DTO；不得向浏览器补发数据库原始行。
- `PREVIEW-MEDIA-P0-05`：图片加载失败、未知 MIME 和缺失角色变体均有稳定尺寸 fallback，不得导致舞台塌缩或使用其他角色媒体。

### 7.3 P1 可部分支持

- `PREVIEW-MEDIA-P1-01`：增加只读媒体缺失报告，将页面期望角色模块与 API 实际公开媒体进行比对。

### 7.4 P2 未来演进

- `PREVIEW-MEDIA-P2-01`：媒体衍生图、CDN 和权限策略由独立媒体规格管理。

### 7.5 关键契约与限制

本轮不扫描、上传、删除、移动或覆盖 MinIO 对象，不修改 `wiki_media_links`，也不根据文件名、拼音或角色编号在浏览器中猜测媒体映射。

## 8. 错误与回退模块

### 8.1 模块职责

保证预览失败不影响正式 Wiki、首页、资料页和问答页，并为真实验收提供明确失败信号。

### 8.2 P0 当前必须满足

- `PREVIEW-ERROR-P0-01`：预览组件错误由独立 Error Boundary 捕获，不能卸载正式应用其他页面。
- `PREVIEW-ERROR-P0-02`：分类 API 失败、列表失败、详情 404、详情 5xx、supplement stale 和媒体失败使用不同状态，不使用同一个空白占位。
- `PREVIEW-ERROR-P0-03`：正式 `/wiki/*` 始终可作为人工回退入口；预览验收前不修改其路由归属。

### 8.3 P1 可部分支持

- `PREVIEW-ERROR-P1-01`：正式替换时保留显式前端回退开关，稳定运行一个验收周期后再删除旧角色组件树。

### 8.4 P2 未来演进

- `PREVIEW-ERROR-P2-01`：接入前端错误遥测和媒体失败统计。

### 8.5 关键契约与限制

预览错误不能触发后端配置重载、RAG `_state` 重置或 Wiki 数据重建。

## 9. 测试与替换门槛模块

### 9.1 模块职责

把“效果好”转换为可复核的功能、真实数据、视觉和安全门槛。

### 9.2 P0 当前必须满足

- `PREVIEW-TEST-P0-01`：所有新增行为使用 TDD；路由、ViewModel、选人交互、详情模块和错误状态必须先出现预期失败测试，再写实现。
- `PREVIEW-TEST-P0-02`：现有前端全部单元测试、TypeScript 和生产构建继续通过；预览不得降低正式 Wiki 测试覆盖。
- `PREVIEW-TEST-P0-03`：使用真实 `:8000/api/wiki/*` 完成至少槲寄生和两名其他角色的选人、详情、媒体和 Back/Forward 验收。
- `PREVIEW-TEST-P0-04`：在 `1280x1024`、`1440x900`、`1920x1080`、`360x800`、`390x844`、`412x915` 检查无横向溢出、重叠、空白舞台和不可达内容。
- `PREVIEW-TEST-P0-05`：以现有批准截图进行同视口对照；关键区域包括 Card Nav、工作区轨道、媒体舞台、身份资料、技能、传承、塑造、语音、文化和藏品。任何缺失模块不得以整体“看起来相似”判定通过。
- `PREVIEW-TEST-P0-06`：浏览器 Network、API 响应和生产产物扫描均不得出现内部 MinIO、本地路径、8001 请求或原型媒体表。
- `PREVIEW-TEST-P0-07`：预览完成后只提交验收证据和替换建议，不自动切换正式路由。

### 9.3 P1 可部分支持

- `PREVIEW-TEST-P1-01`：用户书面批准预览后执行正式路由替换、回退开关验证和新旧视觉对比。

### 9.4 P2 未来演进

- `PREVIEW-TEST-P2-01`：把批准截图纳入稳定的自动视觉差异流水线。

### 9.5 关键契约与限制

单测通过和构建通过只是必要条件，不等于预览通过。真实 API、真实媒体、完整模块和截图对照必须同时满足。

## 10. 与现有实现和规格的关系

- 保留 `2026-07-13-stitch-archival-wiki-global-redesign.md` 的视觉、数据、边界和截图权威；本文只增加并行预览与替换门槛。
- 保留 `2026-07-15-stitch-character-detail-complete-implementation.md` 中已落地的 supplement、API、ViewModel 和角色模块能力；实现时优先复用，不重复建设后端。
- 保留正式 `frontend/react-app/src/api/wiki.ts`、`src/types/wiki.ts`、Card Nav、主题和路由行为。
- `kimi_web` 的布局、字体、纹理和组件结构可迁移；其静态角色数据、模拟媒体表、本地页面状态切换和独立应用壳不迁移。
- 本轮不修改首页、资料页、问答页、RAG、Milvus、MySQL schema、MinIO 对象和媒体映射。

## 11. 已批准决策

- 采用“现有应用内原生预览路由”方案。
- 正式 Wiki 在预览验收前保持不变。
- 预览只消费真实 `/api/wiki/*` 和公开媒体 URL。
- 预览满意后再单独批准正式替换，不在本轮自动切换。

## 12. 2026-07-17 视觉修订

本节记录用户对真实 API 预览页的第二轮截图审查结果，并覆盖本文件中与之冲突的旧描述。

### 12.1 Card Nav

- `PREVIEW-POLISH-P0-01`：PC 选人页和详情页的 Card Nav 顶栏始终常驻视口顶部，左右贴合窗口边界，不再使用居中最大宽度或滚动隐藏；三列菜单仍只在点击菜单按钮后展开，并与顶栏同宽。
- `PREVIEW-POLISH-P0-02`：顶栏使用磨砂背景、边框和分层阴影形成悬浮效果；阴影不能遮挡首屏正文，也不能造成横向滚动。

### 12.2 选人页

- `PREVIEW-POLISH-P0-03`：角色索引优先显示真实大头像。构建层按角色实体 ID 与初始皮肤编号关联资源 manifest；候选资源名采用大小写不敏感、词序无关的 token 匹配，必须同时包含 `headicon`、`large` 和初始皮肤编号，不得只依赖固定的 `Headicon_large-*` 模板。PNG 与 WebP 同时存在时优先 WebP，并建立 `roster_avatar` 映射；React 只消费列表 `thumbnail`，不得拼接文件名、本地路径或 MinIO object key。
- `PREVIEW-POLISH-P0-04`：若共享 MinIO 尚无对应大头像，只允许补充数据构建器把已通过 manifest、SHA-1、MIME 和尺寸校验的对象写入隔离前缀 `wiki-supplement/character/{entity_id}/avatar/`；不得覆盖、删除或扫描反推既有对象。
- `PREVIEW-POLISH-P0-05`：右侧 `PERSONNEL PREVIEW` 将 summary 按空行、换行和 `键: 值` 事实行解析为独立事实与段落；不得把完整原文压成一段连续文本。

### 12.3 详情页

- `PREVIEW-POLISH-P0-06`：PC 详情页正文、字段、技能、文化、藏品和导航文字整体提高约 8% 至 12%，同时保持三列结构和无横向溢出。
- `PREVIEW-POLISH-P0-07`：左列 `ARCHIVE / DATABASE / COMBAT / DOSSIER` 工具区位于左列滚动容器内并使用底部 sticky 定位；滚动档案内容时始终可见。
- `PREVIEW-POLISH-P0-08`：PC 右列 Udimo 档案图片必须受资料列宽度约束，`width/max-width: 100%`，使用 `object-fit: contain`，不得越出页面或覆盖相邻模块。

### 12.4 验收

- `PREVIEW-POLISH-P0-09`：使用 TDD 覆盖大头像媒体映射、缩略图优先级、summary 结构化、工具区 sticky、Udimo 边界、详情字号与全宽常驻顶栏。
- `PREVIEW-POLISH-P0-10`：至少在 `1920x1080`、`1280x951`、`390x844` 重新截图，确认顶栏、列表头像、简介、Udimo 和滚动工具区满足本节要求。
