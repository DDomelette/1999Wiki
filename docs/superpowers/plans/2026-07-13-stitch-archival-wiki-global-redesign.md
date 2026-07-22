# Stitch Archival Wiki 与全站视觉重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Subagents are not allowed; all steps are executed by one agent. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分别以 Stitch `分类选择界面` 和 `个人详情` 为视觉依据，原生重构角色 Wiki 选人页与详情页；先将 `data/raw` 中真实存在的角色档案、传承与塑造补入独立 MySQL supplement，再建立全站 Archival Noir 视觉基础，同时保持 RAG、canonical Wiki 数据、MinIO、`:8000`、稳定 Wiki route 和三屏主站行为不变。

**Architecture:** 保留 processed importer 产出的 `wiki_pages/wiki_media_links` 为 canonical 数据，新增 `rawCharacterEnrichment` 将 `data/raw/100-UTTU人物合辑` 的白名单 profile、传承和塑造幂等写入 `wiki_page_supplements/wiki_supplement_snapshots`；`MySQLWikiRepository` 在读取详情时按 canonical > supplement 合并，并继续通过既有 `content`/`content.blocks` 返回。page list 读链路改为窄列候选排序、筛选指纹 cursor 与外层详情关联，数据库失败不再伪装为空结果。前端保留 `WikiShell` 作为请求控制器，新增纯 `wikiRoutes`、`wikiViewModel`、独立 `WikiCharacterSelectionPage` 与 `WikiCharacterDetailPage`。只有精确 `/wiki/character` 负责选择和预览；任何更深 `/wiki/**` 地址先按完整 pathname 直取详情，404 后才 resolver fallback。两页共享主题、导航、适配器和只读 API，但不共享隐藏分栏 DOM。

**Tech Stack:** React 18、TypeScript 5.5、Vite 5、Zustand、Vitest、Testing Library、Playwright、既有 GSAP/Framer Motion/OGL 动效适配器、Python 3、`python-frontmatter`、`markdown-it-py`、PyMySQL、FastAPI `:8000`、项目 MySQL、共享 MinIO HTTP URL。

## Global Constraints

- 设计规格：`docs/superpowers/specs/2026-07-13-stitch-archival-wiki-global-redesign.md`。
- 计划主线只包含 specs 的 P0；P1 仅列为可选后续子项目，P2 只列入 Deferred。
- 默认主题种子固定为 `#1c110b`、`#e2610b`、`#ed6916`、`#f6ded4`。
- 保留主题 ID `storm-dark`、`manuscript-gold`、`cold-archive` 和存储键 `r1999-theme`，不得无迁移改名。
- 保留 Card Nav、Wiki Scroll Reveal、Tilted Card、问答 Animated List 与 Circular Gallery 当前已经验收的正常模式；仅在 `prefers-reduced-motion`、运行能力不足或既有显式安全模式下降级。本轮不新增未批准的 Stitch 专属动效。
- 精确 `/wiki/character` 是选人页；API 返回的 `page.route` 是规范详情地址。历史 `/wiki/char/:id` 与 importer 可能生成的 `/wiki/character/:id` 都必须兼容，禁止批量改写数据/RAG route。
- 从选人页进入详情前必须写入可恢复的分类、搜索词、选中条目和列表滚动位置；浏览器 Back 是强制验收路径。
- `/wiki` 只请求相对路径 `/api/wiki/*`，正式目标为 FastAPI `:8000`；禁止恢复 8001。
- `data/raw/**` 全部只读；P0 只解析 `100-UTTU人物合辑` 的 104 个角色资料页，不直接把其他目录套入角色 schema。
- 允许新增 Wiki supplement migration/parser/builder，允许最小修改 `src/huiji_wiki/repository.py`、`backend/wiki_schemas.py` 与 `backend/wiki.py` 以完成详情合并、supplement health、page-list cursor 校验和只读错误映射；禁止修改 `backend/main.py`、`src/huiji_wiki/importer.py`、`src/huiji_wiki/content_blocks.py`、RAG `_state`、Milvus、processed artifacts、active pointer 或 MinIO 对象。
- enrichment SQL 只能 CREATE/UPSERT `wiki_page_supplements` 与 `wiki_supplement_snapshots`；禁止 UPDATE/DELETE canonical `wiki_pages`、`wiki_media_links`、`wiki_import_snapshots`、aliases、relations 或 link spans。
- 浏览器只接受 HTTP(S) 媒体 URL；拒绝 `D:\`、`C:\`、`file://` 和容器内部路径。
- 首页、问答页、资料页 P0 只继承视觉基础，不改变三屏滚轮、SSE/问答、媒体分页/播放、资料数据和首页视频行为。
- 所有测试先红后绿；真实数据验收同时固定 `buildVersion + activationEpoch + manifestSha256Prefix + raw sourceRootDigest`。
- Git 提交不是验收门槛；只有用户明确要求时才执行提交。
- 命令默认从 `D:\PycharmProjects\nlp\LangChain\1999Search` 开始；前端 Task 中未显式 `Set-Location` 的 `npm`/`npx` 命令均在 `frontend/react-app` 目录执行。Task 3A 的 Python/MySQL 命令必须显式回到项目根目录。

---

## 1. P0 覆盖矩阵与强制门槛

| Specs P0 | 执行任务 | 强制证据 |
|---|---:|---|
| `VISUAL-P0-01` 至 `VISUAL-P0-08` | Task 1、Task 10 | 令牌单测、全站回归、桌面/移动截图 |
| `NAV-P0-01` 至 `NAV-P0-06` | Task 2、Task 11 | 导航组件测试、键盘/reduced-motion E2E |
| `RAW-P0-01` 至 `RAW-P0-08` | Task 0、Task 3A、Task 8、Task 11 | raw inventory、parser/matcher、SQL 幂等/回滚、API 合并、真实槲寄生与全量覆盖报告 |
| `ADAPTER-P0-01` 至 `ADAPTER-P0-04` | Task 3 | 纯函数测试、输入不可变测试、合并 block 分组证据 |
| `SHELL-P0-01` 至 `SHELL-P0-07` | Task 4、Task 5、Task 11 | 双页面路由/布局测试、历史状态恢复、四视口浏览器验收 |
| `INDEX-P0-01` 至 `INDEX-P0-06` | Task 3B、Task 4、Task 6、Task 11 | 选人预览、无损 cursor、短词搜索、错误传播、API route CTA、Back 恢复、直达详情 E2E |
| `MEDIA-STAGE-P0-01` 至 `MEDIA-STAGE-P0-07` | Task 3、Task 7、Task 11 | 媒体优先级/失败测试、真实 MinIO 图片自然尺寸 |
| `CONTENT-P0-01` 至 `CONTENT-P0-08` | Task 3、Task 8 | block/fallback/link/error-boundary 测试、真实页面 |
| `DOSSIER-P0-01` 至 `DOSSIER-P0-05` | Task 3、Task 9 | 字段/链接/缺失值测试、独立滚动验收 |
| `MAIN-P0-01` 至 `MAIN-P0-03` | Task 1、Task 10、Task 11 | Home/Chat/Data 回归测试与截图 |
| `MOTION-P0-01` 至 `MOTION-P0-03` | Task 2、Task 7、Task 8、Task 10、Task 11 | 既有动效回归、能力降级、reduced-motion E2E |
| `BOUNDARY-P0-01` 至 `BOUNDARY-P0-06` | Task 0、Task 3A、Task 11 | processed/raw 双 snapshot、canonical SQL 哈希、只读网络审计、后端回归、RAG smoke |

显式 P0 覆盖清单（用于执行后逐项核对）：

- Task 1/10：`VISUAL-P0-01`、`VISUAL-P0-02`、`VISUAL-P0-03`、`VISUAL-P0-04`、`VISUAL-P0-05`、`VISUAL-P0-06`、`VISUAL-P0-07`、`VISUAL-P0-08`。
- Task 2/11：`NAV-P0-01`、`NAV-P0-02`、`NAV-P0-03`、`NAV-P0-04`、`NAV-P0-05`、`NAV-P0-06`。
- Task 0/3A/8/11：`RAW-P0-01`、`RAW-P0-02`、`RAW-P0-03`、`RAW-P0-04`、`RAW-P0-05`、`RAW-P0-06`、`RAW-P0-07`、`RAW-P0-08`。
- Task 4/5/11：`SHELL-P0-01`、`SHELL-P0-02`、`SHELL-P0-03`、`SHELL-P0-04`、`SHELL-P0-05`、`SHELL-P0-06`、`SHELL-P0-07`。
- Task 3B/4/6/11：`INDEX-P0-01`、`INDEX-P0-02`、`INDEX-P0-03`、`INDEX-P0-04`、`INDEX-P0-05`、`INDEX-P0-06`。
- Task 3/7/11：`MEDIA-STAGE-P0-01`、`MEDIA-STAGE-P0-02`、`MEDIA-STAGE-P0-03`、`MEDIA-STAGE-P0-04`、`MEDIA-STAGE-P0-05`、`MEDIA-STAGE-P0-06`、`MEDIA-STAGE-P0-07`。
- Task 3/9：`DOSSIER-P0-01`、`DOSSIER-P0-02`、`DOSSIER-P0-03`、`DOSSIER-P0-04`、`DOSSIER-P0-05`。
- Task 3/8：`CONTENT-P0-01`、`CONTENT-P0-02`、`CONTENT-P0-03`、`CONTENT-P0-04`、`CONTENT-P0-05`、`CONTENT-P0-06`、`CONTENT-P0-07`、`CONTENT-P0-08`。
- Task 3：`ADAPTER-P0-01`、`ADAPTER-P0-02`、`ADAPTER-P0-03`、`ADAPTER-P0-04`。
- Task 1/10/11：`MAIN-P0-01`、`MAIN-P0-02`、`MAIN-P0-03`。
- Task 2/7/8/10/11：`MOTION-P0-01`、`MOTION-P0-02`、`MOTION-P0-03`。
- Task 0/3A/11：`BOUNDARY-P0-01`、`BOUNDARY-P0-02`、`BOUNDARY-P0-03`、`BOUNDARY-P0-04`、`BOUNDARY-P0-05`、`BOUNDARY-P0-06`。

任一行缺少自动化证据或真实链路证据，本轮不得标记完成。

## 2. 文件结构决策

### 新建文件

| 文件 | 单一职责 |
|---|---|
| `infra/mysql/migrations/20260713_wiki_page_supplements.sql` | 幂等创建 Wiki supplement 与 snapshot 表，不触碰 canonical 表 |
| `src/huiji_wiki/raw_character_enrichment.py` | raw 角色 frontmatter/Markdown token 解析、精确匹配、稳定 block 与 canonical merge 纯逻辑 |
| `scripts/enrich_wiki_from_raw.py` | dry-run/apply/require-complete、事务写入、canonical 审计与 JSON report CLI |
| `tests/fixtures/huiji_wiki/raw_character_sample.md` | 由真实语法最小化得到的传承/塑造 parser fixture |
| `tests/test_huiji_wiki_raw_character_enrichment.py` | parser、匹配、优先级、幂等、回滚和路径剥离测试 |
| `tests/test_huiji_wiki_supplement_migration.py` | SQL 目标表白名单与 migration 幂等测试 |
| `frontend/react-app/src/styles/archival.css` | 全站档案表面、排版、焦点和状态原语 |
| `frontend/react-app/src/styles/archival.test.ts` | 检查共享视觉原语与禁止旧浅色表面 |
| `frontend/react-app/src/components/wiki/wikiRoutes.ts` | 解析选人页、规范详情 route、展示别名与浏览器历史状态 |
| `frontend/react-app/src/components/wiki/wikiRoutes.test.ts` | 路由分类、别名解析、API route 导航和状态恢复测试 |
| `frontend/react-app/src/components/wiki/wikiViewModel.ts` | API 类型到 Wiki 展示模型的纯函数映射 |
| `frontend/react-app/src/components/wiki/wikiViewModel.test.ts` | 媒体优先级、字段、fallback、不可变性测试 |
| `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.tsx` | `/wiki/character` 的索引、预览、摘要与 CTA 页面 |
| `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.css` | 对照 Stitch `分类选择界面` 的响应式布局 |
| `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.test.tsx` | 选中仅更新预览、CTA route、错误与空态测试 |
| `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.tsx` | 角色规范详情 route 的完整档案页面 |
| `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css` | 对照 Stitch `个人详情` 的响应式布局与滚动边界 |
| `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.test.tsx` | 详情区域、返回入口、直达加载和响应式 DOM 测试 |
| `frontend/react-app/src/components/wiki/WikiErrorBoundary.tsx` | Wiki 详情和单 block 局部错误隔离 |
| `frontend/react-app/src/components/wiki/WikiErrorBoundary.test.tsx` | 局部异常不导致整页白屏 |
| `frontend/react-app/src/components/wiki/WikiHeroStage.tsx` | 透明、稳定尺寸、可降级的通用主媒体舞台 |
| `frontend/react-app/src/components/wiki/WikiHeroStage.test.tsx` | 初始/洞悉、图片失败、候选切换和空态测试 |
| `frontend/react-app/src/components/chat/AnimatedVoiceList.test.tsx` | 语音列表正常动效与 reduced-motion 降级回归 |
| `frontend/react-app/src/components/chat/CircularMediaGallery.test.tsx` | Gallery Canvas/完整 fallback 与可达性回归 |
| `frontend/react-app/e2e/wiki-archival.spec.ts` | 双 Wiki 页面、响应式、历史恢复、只读网络和主站回归验收 |

### 修改文件

- `frontend/react-app/src/main.tsx`：导入共享档案样式。
- `requirements.txt`：显式加入 `markdown-it-py`，不依赖偶然的传递安装。
- `src/huiji_wiki/repository.py`、`tests/test_huiji_wiki_repository.py`：详情读取时合并 supplement、health 读取独立 snapshot；page list 使用无损 opaque cursor、窄列排序并传播数据库失败。
- `backend/wiki.py`、`backend/wiki_schemas.py`、`tests/test_huiji_wiki_api.py`：为 `/api/wiki/health` 增加带默认值的 supplement 状态字段；为 page-list cursor/数据库失败返回明确错误，详情顶层 schema 不变。
- `scripts/verify_huiji_wiki_e2e.py`：增加 supplement completeness、source digest、inheritance/portray、本地路径泄漏、page-list 全量遍历和短词搜索检查。
- `frontend/react-app/src/types/wiki.ts`：增加可选 supplement health 字段，详情仍走既有 `content`/`blocks`。
- `frontend/react-app/src/styles/themes.css`、`themes.test.ts`：三主题语义令牌和字体。
- `frontend/react-app/src/styles/global.css`、`global-background.test.ts`：背景、焦点和自然滚动基础。
- `frontend/react-app/src/App.tsx`、`App.wiki.test.tsx`：所有 Wiki route 进入原生 Wiki 路由控制器，支持 `popstate` 更新。
- `frontend/react-app/src/api/wiki.ts`、`wiki.test.ts`：保留现有请求函数并暴露可识别的 HTTP status error，供 404-only resolver fallback 使用。
- `frontend/react-app/src/components/navigation/RouteAwareCardNav.tsx`、`.test.tsx`、`navigationConfig.ts`：路由感知导航与动态 Wiki 分类。
- `frontend/react-app/src/components/animations/reactbits/CardNav.css`：Stitch 导航外观与视口约束。
- `frontend/react-app/src/components/wiki/WikiShell.tsx`、`.test.tsx`：route 分流、请求状态隔离、别名归一和选人状态恢复。
- `frontend/react-app/src/components/wiki/PageIndex.tsx`、`.css`、`.test.tsx`：选人页档案索引。
- `frontend/react-app/src/components/wiki/PageInfo.tsx`、`.test.tsx`：档案字段与稳定链接。
- `frontend/react-app/src/components/wiki/WikiReader.tsx`：局部错误边界与模板分流。
- `frontend/react-app/src/components/wiki/StructuredContentRenderer.tsx`、`.css`、`.test.tsx`：block 渲染、Scroll Reveal 包装与局部降级。
- `frontend/react-app/src/components/wiki/WikiScrollRevealText.tsx`：保留已验收 Scroll Reveal 与 reduced-motion 行为。
- `frontend/react-app/src/components/wiki/templates/*.tsx`、`WikiTemplates.test.tsx`：新 Dossier 模板层级。
- `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`、`.test.tsx`：初始/洞悉大立绘与 Live2D 共用舞台和 fallback。
- `frontend/react-app/src/components/ui/TiltedImageCard.tsx`：仅做布局兼容，不撤销已验收交互。
- `frontend/react-app/src/components/chat/AnimatedVoiceList.tsx`、`CircularMediaGallery.tsx`：仅在回归失败时修复，不改写为静态列表。
- `frontend/react-app/e2e/wiki-reactbits.spec.ts`：保留既有动效验收，更新已变化的 Wiki 选择/详情断言。
- `frontend/react-app/src/components/sections/HomeSection.test.tsx`、`ChatSection.test.tsx`、`CategoryPanel.test.tsx`：主站行为回归。
- `frontend/react-app/playwright.config.ts`：Stitch 参考视口和新证据目录。

### 生成证据

- `eval/stitch-wiki-p0/baseline-wiki.json`
- `eval/stitch-wiki-p0/baseline-character.json`
- `eval/stitch-wiki-p0/baseline-rag-health.json`
- `eval/stitch-wiki-p0/baseline-raw-catalog.json`
- `eval/stitch-wiki-p0/baseline-raw-character.json`
- `eval/stitch-wiki-p0/forbidden-files.before.sha256`
- `eval/stitch-wiki-p0/raw-character-dry-run.json`
- `eval/stitch-wiki-p0/raw-character-apply.json`
- `eval/stitch-wiki-p0/raw-character-api.json`
- `eval/stitch-wiki-p0/raw-character-second-apply.json`
- `eval/stitch-wiki-p0/wiki-page-list.json`
- `eval/stitch-wiki-p0/canonical-mysql.before.json`
- `eval/stitch-wiki-p0/canonical-mysql.after.json`
- `eval/stitch-wiki-p0/final-wiki.json`
- `eval/stitch-wiki-p0/forbidden-files.after.sha256`
- `eval/stitch-wiki-p0/playwright-report.json`
- `eval/stitch-wiki-p0/screenshots/**`

### 删除文件

- `frontend/react-app/src/components/wiki/wikiLayout.ts`：固定列字符串和已废弃 rail 常量由响应式 CSS 取代。

不得删除 `frontend/react-app/e2e/wiki-reactbits.spec.ts`；新 `wiki-archival.spec.ts` 补充双页面布局验收，不能取代动效回归。

### Task 0: 固定真实数据快照与只读基线

**对应 specs:** `RAW-P0-01`、`RAW-P0-04`、`BOUNDARY-P0-01` 至 `BOUNDARY-P0-06`

**Files:**
- Generate: `eval/stitch-wiki-p0/baseline-wiki.json`
- Generate: `eval/stitch-wiki-p0/baseline-character.json`
- Generate: `eval/stitch-wiki-p0/baseline-rag-health.json`
- Generate: `eval/stitch-wiki-p0/baseline-raw-catalog.json`
- Generate: `eval/stitch-wiki-p0/baseline-raw-character.json`
- Generate: `eval/stitch-wiki-p0/forbidden-files.before.sha256`

**Interfaces:**
- Consumes: `GET :8000/api/wiki/health`、现有 Wiki/MySQL/MinIO 只读链路、完整 `data/raw`、active processed artifacts。
- Produces: 本轮最终验收使用的 `buildVersion`、`activationEpoch`、`manifestSha256Prefix`、752 份 raw 文档目录清单、角色 raw `sourceRootDigest`、104 个角色 source inventory、mixed-document 清单和禁止修改文件哈希。

- [ ] **Step 1: 确认 8000 Wiki 健康且有真实页面**

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/wiki/health" | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/wiki/pages?limit=3" | ConvertTo-Json -Depth 8
```

Expected: `ready=true`、`stale=false`、`pageCount>0`，页面 `items` 非空。失败则停止执行，不以 mock 数据继续。

- [ ] **Step 2: 固定一条真实角色规范 route 与媒体语义样本**

```powershell
New-Item -ItemType Directory -Force eval/stitch-wiki-p0 | Out-Null
$client = New-Object System.Net.WebClient
$listJson = [Text.Encoding]::UTF8.GetString($client.DownloadData("http://127.0.0.1:8000/api/wiki/pages?type=character&q=%E6%A7%B2%E5%AF%84%E7%94%9F&limit=10"))
$character = ($listJson | ConvertFrom-Json).items | Where-Object { $_.title -eq '槲寄生' } | Select-Object -First 1
if (-not $character.route) { throw 'Character route missing' }
$route = [Uri]::EscapeDataString($character.route)
$detailJson = [Text.Encoding]::UTF8.GetString($client.DownloadData("http://127.0.0.1:8000/api/wiki/pages/by-route?route=$route"))
$client.Dispose()
$detail = $detailJson | ConvertFrom-Json
$detail | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 eval/stitch-wiki-p0/baseline-character.json
```

Expected: 锁定真实槲寄生实体；`detail.route` 与 list item `route` 完全一致，记录实际规范模式而不预设重写。至少一条公开 HTTP 图片媒体可读。baseline 中允许尚无 inheritance/portray，但必须明确记录缺失，供 enrichment 后对比。

- [ ] **Step 3: 固定完整 raw 目录与 mixed-document 基线**

只读递归枚举 `data/raw`，按一级目录记录 Markdown 数、非 Markdown 数和排序后相对路径摘要；另扫描角色形态章节（至少 `## 传承`、`## 塑造`），将角色主目录之外的命中项写入 `mixedDocuments`：

```powershell
eval/stitch-wiki-p0/baseline-raw-catalog.json
```

Expected: `markdownCount=752`、`nonMarkdownCount=0`；一级目录计数固定为 `105/90/46/1/4/506`；`mixedDocuments` 明确包含 `500-箱外阵营/勿忘我｜Forget Me Not.md`，并标记 `deferredPolicy=mixed-document`。目录计数或文件类型变化时先人工审查，不把非角色文档送入 P0 角色 parser；对应 typed enrichment 只保留在本 plan 的 P1 可选后续子项目。

- [ ] **Step 4: 固定 raw 角色 inventory 与 processed 匹配基线**

使用 PowerShell 只读枚举 `data/raw/100-UTTU人物合辑/**/*.md`，排除 `100-UTTU人物合辑.md`；每项记录相对路径、SHA-256、`Name`、是否有 `## 传承`、是否有 `## 塑造`，并汇总 frontmatter `profileFieldCoverage`。再分别从 `data/processed/huiji/dev/parent_blocks.jsonl` 提取唯一 character `entity_name`、从项目 MySQL 只读查询 `wiki_pages(page_id,title)` 的 character 行，按 NFC 与 trim 后 exact 比较；最后按排序后的 `relativePath:sha256` 计算 `sourceRootDigest`，写入：

```powershell
eval/stitch-wiki-p0/baseline-raw-character.json
```

Expected: `sourceCount=104`、`inheritanceCount=104`、`portrayCount=104`、`exactProcessedNameMatches=104`、`exactMySQLTitleMatches=104`、`unmatched=[]`、`ambiguous=[]`；MySQL 当前 character 行为 132；`初始立绘/本色立绘=104`，`银行彩色相片/征集/出场章节=103`。若实际源或 canonical snapshot 已变化，先人工审查新 inventory 并更新本 plan 的快照说明，不能忽略差异继续。

- [ ] **Step 5: 生成只读 Wiki 基线报告**

```powershell
python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --limit 30 --check-media --media-sample-limit 5 --inspection-label stitch-wiki-before --output eval/stitch-wiki-p0/baseline-wiki.json
```

Expected: exit `0`，`local path leak count: 0`、`http media url count > 0`。

- [ ] **Step 6: 保存 RAG 健康与禁止修改文件哈希**

```powershell
New-Item -ItemType Directory -Force eval/stitch-wiki-p0 | Out-Null
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 eval/stitch-wiki-p0/baseline-rag-health.json
Get-FileHash backend/main.py,src/huiji_wiki/importer.py,src/huiji_wiki/content_blocks.py,src/rag/vectorstore.py,data/processed/huiji/dev/parent_blocks.jsonl,data/processed/huiji/dev/child_blocks.jsonl,data/processed/huiji/dev/media_assets.jsonl -Algorithm SHA256 | ConvertTo-Json | Set-Content -Encoding UTF8 eval/stitch-wiki-p0/forbidden-files.before.sha256
```

Expected: 六个基线证据文件存在且可解析。

- [ ] **Step 7: 运行现有前后端基线测试**

```powershell
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q
Set-Location frontend/react-app
npm test
```

Expected: 两组命令均 exit `0`。若存在基线失败，先记录并由用户决定，不能把旧失败归入本轮。

### Task 1: Archival Noir 三主题与共享视觉原语

**对应 specs:** `VISUAL-P0-01` 至 `VISUAL-P0-08`、`MAIN-P0-01`、`MAIN-P0-03`

**Files:**
- Create: `frontend/react-app/src/styles/archival.css`
- Create: `frontend/react-app/src/styles/archival.test.ts`
- Modify: `frontend/react-app/src/styles/themes.css`
- Modify: `frontend/react-app/src/styles/themes.test.ts`
- Modify: `frontend/react-app/src/styles/global.css`
- Modify: `frontend/react-app/src/main.tsx`

**Interfaces:**
- Produces: `--archive-*`、`--status-*`、`--link-accent`、`.archive-surface`、`.archive-kicker`、`.archive-meta`。
- Consumers: Card Nav、Wiki Dossier、Home/Chat/Data 现有组件。

- [ ] **Step 1: 写主题令牌失败测试**

在 `themes.test.ts` 增加：

```ts
it('uses the approved Archival Noir seeds and complete semantic roles', () => {
  const dark = themes.split('[data-theme="storm-dark"] {')[1]?.split('}')[0] ?? ''
  for (const seed of ['#1c110b', '#e2610b', '#ed6916', '#f6ded4']) expect(dark).toContain(seed)
  for (const token of ['--archive-panel', '--archive-line', '--link-accent', '--status-success', '--status-warning', '--status-error']) {
    expect(dark).toContain(token)
  }
})
```

- [ ] **Step 2: 验证测试先失败**

```powershell
Set-Location frontend/react-app
npx vitest run src/styles/themes.test.ts
```

Expected: FAIL，缺少 Archival Noir 种子或新语义令牌。

- [ ] **Step 3: 写入三主题完整语义令牌**

`storm-dark` 必须精确包含：

```css
[data-theme="storm-dark"] {
  --bg-base: #1c110b;
  --bg-primary: #1c110b;
  --bg-elevated: #27170f;
  --bg-overlay: rgba(28, 17, 11, 0.9);
  --text-primary: #f6ded4;
  --text-secondary: #c8aaa0;
  --text-muted: #967a70;
  --accent-gold: #e2610b;
  --accent-rust: #ed6916;
  --accent-purple: #8d5135;
  --border-subtle: rgba(226, 97, 11, 0.28);
  --border-card: rgba(237, 105, 22, 0.5);
  --border-glow: rgba(237, 105, 22, 0.3);
  --archive-panel: rgba(28, 17, 11, 0.82);
  --archive-panel-strong: rgba(20, 11, 7, 0.94);
  --archive-line: rgba(226, 97, 11, 0.42);
  --link-accent: #77a9d6;
  --status-success: #7fa37d;
  --status-warning: #ed9b45;
  --status-error: #d96b62;
  --shadow-card: 0 14px 40px rgba(0, 0, 0, 0.38);
}
```

另外两套主题使用以下精确值，不得删除现有主题 ID：

```css
[data-theme="manuscript-gold"] {
  --bg-base: #f1e6d2;
  --bg-primary: #f1e6d2;
  --bg-elevated: #f8f0e2;
  --bg-overlay: rgba(241, 230, 210, 0.92);
  --text-primary: #2d1a12;
  --text-secondary: #5f473b;
  --text-muted: #80695c;
  --accent-gold: #a9470a;
  --accent-rust: #c6570d;
  --accent-purple: #6f5d72;
  --border-subtle: rgba(92, 52, 27, 0.22);
  --border-card: rgba(169, 71, 10, 0.42);
  --border-glow: rgba(198, 87, 13, 0.24);
  --archive-panel: rgba(248, 240, 226, 0.86);
  --archive-panel-strong: rgba(248, 240, 226, 0.97);
  --archive-line: rgba(169, 71, 10, 0.4);
  --link-accent: #1d5f99;
  --status-success: #3f7147;
  --status-warning: #a85d13;
  --status-error: #a33e35;
  --shadow-card: 0 14px 36px rgba(61, 36, 20, 0.18);
}

[data-theme="cold-archive"] {
  --bg-base: #11191a;
  --bg-primary: #11191a;
  --bg-elevated: #182426;
  --bg-overlay: rgba(17, 25, 26, 0.91);
  --text-primary: #dce4df;
  --text-secondary: #a8b7b1;
  --text-muted: #748984;
  --accent-gold: #c65d20;
  --accent-rust: #e47731;
  --accent-purple: #708b88;
  --border-subtle: rgba(111, 143, 138, 0.26);
  --border-card: rgba(198, 93, 32, 0.46);
  --border-glow: rgba(228, 119, 49, 0.25);
  --archive-panel: rgba(17, 25, 26, 0.84);
  --archive-panel-strong: rgba(12, 19, 20, 0.95);
  --archive-line: rgba(198, 93, 32, 0.4);
  --link-accent: #76a8d2;
  --status-success: #78a487;
  --status-warning: #d59448;
  --status-error: #d26f67;
  --shadow-card: 0 14px 40px rgba(0, 0, 0, 0.4);
}
```

`[data-theme]` 字体定义改为：

```css
[data-theme] {
  --font-body: 'LXGW WenKai', 'Noto Serif SC', 'Songti SC', serif;
  --font-display: 'Libre Caslon Text', 'Noto Serif SC', Georgia, serif;
  --font-mono: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
}
```

- [ ] **Step 4: 新增共享档案原语并导入**

`archival.css` 至少实现：

```css
.archive-surface { background: var(--archive-panel); border: 1px solid var(--archive-line); border-radius: 2px; }
.archive-kicker { color: var(--accent-rust); font: 600 .72rem/1.3 var(--font-mono); text-transform: uppercase; }
.archive-meta { color: var(--text-secondary); font: .78rem/1.55 var(--font-mono); overflow-wrap: anywhere; }
:where(a, button, input, [tabindex]):focus-visible { outline: 2px solid var(--accent-rust); outline-offset: 3px; }
.archive-error { color: var(--status-error); border-left: 2px solid currentColor; padding-left: .75rem; }
.archive-empty { color: var(--text-muted); font-family: var(--font-mono); }
```

并在 `main.tsx` 中紧跟 `themes.css` 导入：

```ts
import './styles/archival.css'
```

- [ ] **Step 5: 增加原语测试并验证通过**

`archival.test.ts` 使用 `readFileSync` 断言上述类、焦点规则以及不存在 `#f5ead0`、`#fff8e8` 等旧浅色页面填充。运行：

```powershell
npx vitest run src/styles/themes.test.ts src/styles/archival.test.ts src/styles/global-background.test.ts src/store/themeStore.test.ts
```

Expected: PASS；现有 `r1999-theme` 迁移测试继续通过。

### Task 2: Stitch 风格 RouteAwareCardNav

**对应 specs:** `NAV-P0-01` 至 `NAV-P0-06`、`MOTION-P0-01`、`MOTION-P0-03`

**Files:**
- Modify: `frontend/react-app/src/components/navigation/RouteAwareCardNav.tsx`
- Modify: `frontend/react-app/src/components/navigation/navigationConfig.ts`
- Modify: `frontend/react-app/src/components/navigation/RouteAwareCardNav.test.tsx`
- Modify: `frontend/react-app/src/components/animations/reactbits/CardNav.css`

**Interfaces:**
- Consumes: `WikiCategoryItem[]`、`onCategorySelect(key)`、`ThemeToggle`。
- Produces: 主站一级 `WIKI -> /wiki/character`、Wiki 一级 `首页 -> /`、动态分类菜单和 Card Nav 既有动效。

- [ ] **Step 1: 写导航失败测试**

新增测试覆盖：所有传入分类均出现、点击分类传回 key、主题按钮位于一级入口左侧、DOM 不存在 Sidebar/CategoryRail、`prefers-reduced-motion` 时菜单仍可见可操作。

```ts
expect(screen.getByRole('button', { name: '角色 30' })).toBeEnabled()
expect(screen.getByRole('button', { name: '剧情 12' })).toBeEnabled()
expect(screen.getByRole('link', { name: 'WIKI' })).toHaveAttribute('href', '/wiki/character')
expect(screen.getByRole('link', { name: '首页' })).toHaveAttribute('href', '/')
expect(document.querySelector('[data-testid="wiki-category-rail"]')).toBeNull()
```

- [ ] **Step 2: 运行导航测试并确认失败点**

```powershell
npx vitest run src/components/navigation/RouteAwareCardNav.test.tsx
```

Expected: 新增的 Archival class、视口约束或 reduced-motion 标记断言先失败。

- [ ] **Step 3: 收敛导航结构和样式**

保持现有 `CardNav` GSAP 生命周期；在 `RouteAwareCardNav` 根调用中增加 `context` 和稳定 archive class/data 属性，不新增第二导航。`CardNav.css` 使用：

```css
.card-nav { width: min(1180px, calc(100vw - 24px)); color: var(--text-primary); }
.card-nav__bar, .card-nav__menu { background: var(--archive-panel-strong); border: 1px solid var(--archive-line); border-radius: 2px; }
.card-nav__menu { max-height: calc(100dvh - 92px); overflow-y: auto; }
.card-nav__brand, .card-nav__group h2 { font-family: var(--font-mono); letter-spacing: 0; }
.card-nav__primary { color: var(--accent-rust); font-family: var(--font-mono); }
@media (max-width: 720px) { .card-nav__menu { grid-template-columns: 1fr; } }
```

除将主站 `WIKI` 入口规范化为 `/wiki/character` 外，不得改变 `mainNavigation()` 和 `wikiNavigation()` 的业务动作；只允许调整标签顺序、禁用状态和视觉元数据。分类选择仍通过 `onCategorySelect` 更新选人查询，不在导航内部请求详情。

- [ ] **Step 4: 运行导航和主题测试**

```powershell
npx vitest run src/components/navigation/RouteAwareCardNav.test.tsx src/store/themeStore.test.ts src/styles/themes.test.ts
```

Expected: PASS。

### Task 3: 纯 WikiViewModel 适配层

**对应 specs:** `ADAPTER-P0-01` 至 `ADAPTER-P0-04`、`MEDIA-STAGE-P0-04`、`MEDIA-STAGE-P0-06`、`CONTENT-P0-01`、`CONTENT-P0-02`、`DOSSIER-P0-01`、`DOSSIER-P0-05`

**Files:**
- Create: `frontend/react-app/src/components/wiki/wikiViewModel.ts`
- Create: `frontend/react-app/src/components/wiki/wikiViewModel.test.ts`

**Interfaces:**
- Produces:

```ts
export interface WikiIndexItemViewModel { pageId: string; title: string; meta: string; thumbnail: string; route: string }
export interface WikiMediaViewModel { id: string; title: string; url: string; kind: 'portrait' | 'image' | 'voice'; variant: 'initial' | 'insight' | 'unspecified'; priority: number }
export interface WikiPortraitSlots { initial: WikiMediaViewModel | null; insight: WikiMediaViewModel | null; extras: WikiMediaViewModel[] }
export interface WikiCharacterSectionGroups {
  profile: WikiContentBlock[]
  skills: WikiContentBlock[]
  inheritance: WikiContentBlock[]
  portray: WikiContentBlock[]
  voices: WikiContentBlock[]
  archive: WikiContentBlock[]
  remainder: WikiContentBlock[]
}
export interface WikiDossierField { label: string; value: string; href?: string }
export interface WikiPageViewModel {
  page: WikiPageDetail
  portraits: WikiMediaViewModel[]
  portraitSlots: WikiPortraitSlots
  images: WikiMediaViewModel[]
  voices: WikiMediaViewModel[]
  primaryMedia: WikiMediaViewModel | null
  live2dAvailable: false
  profileFacts: WikiDossierField[]
  dossier: WikiDossierField[]
  blocks: WikiContentBlock[]
  characterSections: WikiCharacterSectionGroups
  fallbackText: string
}
export function buildWikiIndexItem(page: WikiPageListItem): WikiIndexItemViewModel
export function buildWikiPageViewModel(page: WikiPageDetail): WikiPageViewModel
export function buildFallbackBlocks(text: string): WikiContentBlock[]
export function isPublicHttpUrl(value: unknown): value is string
```

- [ ] **Step 1: 写纯函数失败测试**

测试必须包含：显式 `initial_portrait`/`insight_portrait` role 可形成两个槽位、普通 `portrait` 保持 `unspecified`、文件名 `_p` 或数字后缀不能自行产生“洞悉”语义、voice 不进入主图、非 HTTP URL 被剔除、aliases 缺失显示“无”、`content.profile` 的介质/属性/角色灵感/伤害类型/传承/定位标签/香调/衣着描述被稳定映射、合并后的 blocks 优先、`profile/skill/ultimate/inheritance/portray/voice/dossier/culture/item` section 被稳定分组、未知 section 进入 remainder、长 fallback 按自然段/句末分块、输入对象序列化前后相同。

```ts
const before = JSON.stringify(page)
const view = buildWikiPageViewModel(page)
expect(view.portraitSlots.initial?.id).toBe('initial')
expect(view.portraitSlots.insight?.id).toBe('insight')
expect(view.portraits.find((item) => item.title.includes('_p'))?.variant).toBe('unspecified')
expect(view.live2dAvailable).toBe(false)
expect(view.voices).toHaveLength(1)
expect(view.dossier).toContainEqual({ label: 'Route', value: '/wiki/char/3003', href: '/wiki/char/3003' })
expect(JSON.stringify(page)).toBe(before)
```

- [ ] **Step 2: 运行测试验证失败**

```powershell
npx vitest run src/components/wiki/wikiViewModel.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 URL、媒体和字段集中映射**

媒体分类必须固定，且只读取公开 API 字段：

```ts
function portraitVariant(item: Record<string, unknown>): WikiMediaViewModel['variant'] {
  const role = String(item.role ?? item.assetType ?? item.asset_type ?? '').toLowerCase()
  const semanticTitle = String(item.title ?? '').toLowerCase()
  if (['initial_portrait', 'portrait_initial'].includes(role) || /(^|[\s：:])初始立绘([\s：:]|$)/.test(semanticTitle)) return 'initial'
  if (['insight_portrait', 'portrait_insight'].includes(role) || /(^|[\s：:])洞悉立绘([\s：:]|$)/.test(semanticTitle)) return 'insight'
  return 'unspecified'
}

export function isPublicHttpUrl(value: unknown): value is string {
  return typeof value === 'string' && /^https?:\/\//i.test(value)
}
```

`primaryMedia` 顺序为明确 initial -> 第一张 unspecified portrait -> 明确 insight -> 其他 image。不得解析 URL、object key、`_p`、`300301` 等文件命名来推断皮肤。若真实 API 没有明确 initial/insight 语义，P0 仍可展示通用立绘切换，但标签必须是“立绘 1/立绘 2”，不得伪装成初始/洞悉；补充语义映射属于独立数据/API 契约变更。

`characterSections` 只按 API block 的 `section` 精确分组：`profile -> profile`，`skill|ultimate -> skills`，`inheritance -> inheritance`，`portray -> portray`，`voice -> voices`，`dossier|culture|item|items -> archive`，其他进入 `remainder`。不得根据中文正文关键词推断传承、塑造或技能语义；raw supplement 已提供明确 section，匹配角色若任一组为空视为数据链路失败，而不是正常占位。

`dossier` 固定生成 Source、Category、Type、Page ID、Assets、Relations、Links、Aliases、Route；Aliases 只读取 `content.aliases` 的字符串数组，不从标题猜测。

`profileFacts` 只读取 API 合并后的 `content.profile` 白名单；array 保持原顺序并以可换行标签组呈现，空值不生成行。字段展示顺序固定为介质、星级、属性、角色灵感、伤害类型、传承、Udimo、生日、定位标签、香调、初始衣着、洞悉本色、出场章节，不把 raw source key 或诊断混入界面。

- [ ] **Step 4: 实现保守 fallback 分块**

算法顺序固定为：标准化换行 -> 空行分段 -> `#` 标题 -> `标签：值` 字段 -> 超过 240 字的普通段落按 `。！？!?` 句末聚合为不超过约 240 字的段落。不得生成技能、稀有度、阵营或关系语义。

- [ ] **Step 5: 运行适配器测试**

```powershell
npx vitest run src/components/wiki/wikiViewModel.test.ts
```

Expected: PASS，无网络 mock，证明函数不访问 fetch/React state。

### Task 3A: raw 角色解析、MySQL supplement 与 API 合并

**对应 specs:** `RAW-P0-01` 至 `RAW-P0-08`、`CONTENT-P0-01`、`CONTENT-P0-03`、`BOUNDARY-P0-01` 至 `BOUNDARY-P0-06`

**Files:**
- Modify: `requirements.txt`
- Create: `infra/mysql/migrations/20260713_wiki_page_supplements.sql`
- Create: `src/huiji_wiki/raw_character_enrichment.py`
- Create: `scripts/enrich_wiki_from_raw.py`
- Create: `tests/fixtures/huiji_wiki/raw_character_sample.md`
- Create: `tests/test_huiji_wiki_raw_character_enrichment.py`
- Create: `tests/test_huiji_wiki_supplement_migration.py`
- Modify: `src/huiji_wiki/repository.py`
- Modify: `tests/test_huiji_wiki_repository.py`
- Modify: `backend/wiki_schemas.py`
- Modify: `tests/test_huiji_wiki_api.py`
- Modify: `scripts/verify_huiji_wiki_e2e.py`
- Modify: `frontend/react-app/src/types/wiki.ts`
- Generate: `eval/stitch-wiki-p0/raw-character-dry-run.json`
- Generate: `eval/stitch-wiki-p0/raw-character-apply.json`
- Generate: `eval/stitch-wiki-p0/raw-character-api.json`
- Generate: `eval/stitch-wiki-p0/raw-character-second-apply.json`
- Generate: `eval/stitch-wiki-p0/canonical-mysql.before.json`
- Generate: `eval/stitch-wiki-p0/canonical-mysql.after.json`

**Interfaces:**

```python
@dataclass(frozen=True)
class RawCharacterSource:
    source_key: str
    source_sha256: str
    profile: dict[str, object]
    blocks: tuple[dict[str, object], ...]

@dataclass(frozen=True)
class WikiSupplementPayload:
    page_id: str
    source_kind: str
    source_key: str
    source_sha256: str
    profile: dict[str, object]
    blocks: tuple[dict[str, object], ...]
    diagnostics: dict[str, object]

def parse_raw_character(path: Path, source_root: Path) -> RawCharacterSource: ...
def match_raw_characters(sources, character_pages, aliases) -> tuple[list[WikiSupplementPayload], EnrichmentReport]: ...
def merge_supplement_content(canonical: dict[str, object], supplement: WikiSupplementPayload | None) -> dict[str, object]: ...
```

CLI 固定支持：

```text
--source-root PATH
--dry-run | --apply
--require-complete
--migrate
--report PATH
--canonical-before PATH
--canonical-after PATH
```

- [ ] **Step 1: 写 parser、匹配、merge 与 migration 失败测试**

最小 fixture 必须保留真实语法特征：YAML list、Obsidian wikilink、`## 传承：木秀于林`、内联洞悉图片、粗体效果、脚注、`## 塑造`、说明段落和 `LV.1..LV.5` 表格。测试断言：

1. profile 只输出 specs 白名单，list 保持数组，日期作为字符串，不返回 `cssclasses/tags/banner_header`；缺失的可选字段保持缺失，不用空模板或其他角色值补齐。
2. `inheritance` 的效果行数可为 1、2 或 3，不写死；`portray` 恰好保留五个等级和说明段落。
3. block ID 在同一 `page_id/source_kind/section/ordinal` 下稳定；改正文只改变 digest，不产生重复 ID。
4. `[[target|label]]` 与 `[[target\|label]]` 只保留 `label`，无 label 时保留安全的目标显示名；输出 block 不包含 `assets/`、`../`、`D:\`、`file://`、Markdown/Obsidian 图片目标或原始 frontmatter。
5. exact `Name` 唯一匹配成功；unmatched/ambiguous 阻止 `require_complete`；不执行 fuzzy/substring。
6. canonical 已有 `inheritance` 时 supplement 同 section 让位；缺失时注入；canonical route/title/source/media 不变。
7. migration 只创建两个 supplement 表；测试拒绝出现 `UPDATE wiki_pages`、`DELETE FROM wiki_` canonical 表或 MinIO/Milvus 语句。

```powershell
Set-Location D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_raw_character_enrichment.py tests/test_huiji_wiki_supplement_migration.py -q
```

Expected: FAIL，模块、fixture 和 migration 尚不存在。

- [ ] **Step 2: 加入显式 Markdown parser 依赖并创建幂等 migration**

在 `requirements.txt` 增加受控 `markdown-it-py` 版本；保留现有 `python-frontmatter` 和 `pymysql`。migration 使用 `CREATE TABLE IF NOT EXISTS` 创建 specs 15.5 定义的两个表；不设置会在 canonical rebuild 时误删 supplement 的 destructive trigger，不修改现有表结构。

- [ ] **Step 3: 实现结构化 raw parser**

算法顺序固定：

1. `frontmatter.load()` 读取 YAML，NFC 标准化 key/value，按字段白名单投影。
2. `MarkdownIt('commonmark').enable('table')` 产生 token；只从二级标题边界提取 `传承` 和 `塑造`。
3. inline token 转可读纯文本：保留 Markdown link label、粗体文本、等级与百分比，丢弃 image destination/HTML wrapper/脚注标记；对 token 内残留的 Obsidian `[[target|label]]` 或 `[[target\|label]]` 仅做局部、锚定的 label 提取，不在全文上做正则清洗，也不读取本地图片字节。
4. 传承输出 heading + table；塑造输出可选说明 paragraph + table。table 第一行是表头，数据行不得因 alignment row 或内联图片丢失。
5. 对每个源文件计算 SHA-256；对排序后的 `source_key:sha256` 计算 `sourceRootDigest`。

不要调用 `src.utils.text_cleaner.clean_markdown()`，也不要用一个跨全文正则截取所有 Markdown。

- [ ] **Step 4: 实现精确匹配、全量门槛和事务 writer**

从 MySQL 只读 `wiki_pages(page_id,page_type,title)` 与 `wiki_aliases`；只考虑 `page_type='character'`。匹配顺序为 exact normalized Name、唯一 exact exonym、唯一 exact alias。writer 在写入前完成全部解析与匹配，并计算 canonical digest；`--apply` 在单事务中 upsert supplement rows 和 snapshot。异常、unmatched 或 ambiguous 在 `--require-complete` 下 rollback。

canonical digest 覆盖 `wiki_pages`、`wiki_media_links`、`wiki_import_snapshots`、`wiki_aliases`、`wiki_relations`、`wiki_link_spans` 的排序后只读摘要；apply 前后必须一致。supplement snapshot 另记录当前 `wiki_import_snapshots.snapshot_sha256`，供 canonical 重导后的 stale 判断。报告至少包含：source/matched/unmatched/ambiguous counts、section counts、profile coverage、inserted/updated/unchanged、sourceRootDigest、canonicalSnapshotSha256、canonicalBeforeDigest、canonicalAfterDigest、conflicts 和 errors。

- [ ] **Step 5: 实现 repository 合并与 health 状态**

`get_page_detail()` 在取得 canonical page 后按 `page_id + source_kind='obsidian_character'` 读取 supplement：

- `content.profile` 采用 canonical 非空字段优先，raw 只补空值；raw 专属字段直接加入 profile。
- `content.blocks` 按 section 去重；canonical 已有同名 section 时 supplement 不注入并记录 conflict。
- 返回前删除 `source_key/source_sha256/diagnostics`，只允许公开 `supplementVersion` 与 `supplementSections`。
- `/api/wiki/health` 增加默认安全字段：`supplementReady`、`supplementPageCount`、`supplementBlockCount`、`supplementSourceDigestPrefix`、`supplementStale`。`supplementStale` 比较 supplement 记录的 canonical snapshot 与当前 `wiki_import_snapshots`；raw 文件的实时 digest 只由 builder/verifier 计算，避免普通 health 请求重复读取 104 个文件。旧表尚未迁移时返回默认值，不让 canonical Wiki 白屏；不修改 `/health`。

Task 3A 内所有 list/search/route 语义不变，不修改 `backend/wiki.py` 或详情 response 的顶层 schema；page-list cursor 与错误映射只在后续 Task 3B 按独立测试修改。

- [ ] **Step 6: 运行 enrichment、repository 与 API 单测**

```powershell
python -m pytest tests/test_huiji_wiki_raw_character_enrichment.py tests/test_huiji_wiki_supplement_migration.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py -q
```

Expected: PASS；包括缺表 fallback、canonical conflict、路径剥离、事务 rollback 和 health 默认值。

- [ ] **Step 7: 对真实 104 个角色执行 require-complete dry-run**

```powershell
python scripts/enrich_wiki_from_raw.py --source-root "data/raw/100-UTTU人物合辑" --dry-run --require-complete --report eval/stitch-wiki-p0/raw-character-dry-run.json --canonical-before eval/stitch-wiki-p0/canonical-mysql.before.json
```

Expected: exit `0`；`sourceCount=104`、`matchedCount=104`、`inheritanceCount=104`、`portrayCount=104`、`unmatched=[]`、`ambiguous=[]`、`writes=0`；报告中的 `profileFieldCoverage` 与 Task 0 一致，包括三个 103/104 可选字段。`sourceRootDigest` 必须等于 Task 0 baseline；否则停止并重新固定 source inventory。

- [ ] **Step 8: 迁移并事务 apply**

```powershell
python scripts/enrich_wiki_from_raw.py --source-root "data/raw/100-UTTU人物合辑" --apply --migrate --require-complete --report eval/stitch-wiki-p0/raw-character-apply.json --canonical-before eval/stitch-wiki-p0/canonical-mysql.before.json --canonical-after eval/stitch-wiki-p0/canonical-mysql.after.json
```

Expected: exit `0`；supplement page count 104，inheritance/portray 均 104；canonical before/after digest 相同；只创建/写入两个 supplement 表。任何 canonical digest 差异立即失败并回滚。

- [ ] **Step 9: 重启 8000 并验证真实 API 合并**

按项目既有方式重启 FastAPI，使代码与依赖加载一致；不要清理 `get_config()` cache 或 RAG `_state`。然后：

```powershell
python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --require-supplement --expected-supplement-pages 104 --sample-title "槲寄生" --inspection-label raw-character-api --output eval/stitch-wiki-p0/raw-character-api.json
```

Expected: exit `0`；详情含“木秀于林”、洞悉表和 `LV.1..LV.5`；health `supplementReady=true`、`supplementPageCount=104`、`supplementStale=false`；响应无 raw/source path。中文 JSON 由 Python 客户端按 UTF-8 解码，不使用 Windows PowerShell 5.1 的默认响应解码。

- [ ] **Step 10: 重跑 apply 证明幂等**

```powershell
python scripts/enrich_wiki_from_raw.py --source-root "data/raw/100-UTTU人物合辑" --apply --require-complete --report eval/stitch-wiki-p0/raw-character-second-apply.json
```

Expected: exit `0`；`inserted=0`、`updated=0`、`unchanged=104`，snapshot digest 不变，canonical digest 不变。

### Task 3B: Wiki page-list 无损 cursor、窄列搜索与错误传播

**对应 specs:** `INDEX-P0-04` 至 `INDEX-P0-06`、`BOUNDARY-P0-05`

**Files:**
- Modify: `src/huiji_wiki/repository.py`
- Modify: `tests/test_huiji_wiki_repository.py`
- Modify: `backend/wiki.py`
- Modify: `tests/test_huiji_wiki_api.py`
- Modify: `scripts/verify_huiji_wiki_e2e.py`
- Generate: `eval/stitch-wiki-p0/wiki-page-list.json`

**Interfaces:**

```python
@dataclass(frozen=True)
class WikiListCursor:
    version: int
    offset: int
    filter_fingerprint: str

class InvalidWikiCursor(ValueError): ...
class WikiRepositoryUnavailable(RuntimeError): ...

def encode_wiki_list_cursor(cursor: WikiListCursor) -> str: ...
def decode_wiki_list_cursor(value: str, *, expected_fingerprint: str) -> WikiListCursor: ...
```

cursor 使用 URL-safe Base64 JSON，payload 固定为 `{"v":1,"o":offset,"f":fingerprint}`；`fingerprint = sha256(category + "\0" + q + "\0" + page_type)[:16]`。cursor 是 API 不透明值，不写入 route、localStorage 或 MySQL。

- [ ] **Step 1: 写现有漏项、宽搜索和异常吞噬的失败测试**

在 repository/API 测试中覆盖：

1. 将现有“extra row 作为 cursor”的测试改为两页连续读取：`limit=2` 时第一页返回前两行，第二页必须包含原第 3 行；累计 page ID 无缺失、无重复。
2. cursor round-trip 保持 offset/fingerprint；损坏 payload 或把旧查询 cursor 用于新查询时抛 `InvalidWikiCursor`，API 返回 `400`。
3. 搜索 SQL 的排序子查询只携带 `page_id/title/subtitle/source_title/match_rank/alias_priority`，`content_json` 只能在完成 `ORDER BY + LIMIT/OFFSET` 后由外层 join 读取。
4. exact title、title contains、exact alias、alias contains、subtitle、source title 的既有优先级不变；alias 在候选子查询中一次聚合，不重复执行多个相关子查询。
5. PyMySQL 查询失败抛 `WikiRepositoryUnavailable`，API 返回 `503`；不得返回 `([], None)` 或 `200 + items=[]`。
6. verifier 能按 opaque `nextCursor` 遍历到 `category.count`，检测重复/漏项，并接受多个 `--search-probe`。

```powershell
Set-Location D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py tests/test_huiji_wiki_e2e_script.py -q
```

Expected: FAIL；当前实现会跳过 extra row，宽查询可能触发 MySQL `ERROR 1038`，数据库异常被吞成空结果。

- [ ] **Step 2: 实现筛选指纹 opaque cursor**

cursor 解码必须验证版本、非负 offset 和筛选指纹；不得接受任意 SQL 片段、page ID 比较表达式或前端构造字段。第一页 offset 为 0；若本页取得 `limit + 1` 行，则只返回前 `limit` 行，并将下一 cursor 写为 `offset + limit`。额外探测行不进入 cursor，也不会在下一页被跳过。

- [ ] **Step 3: 将 page-list SQL 改为窄列候选排序**

使用 CTE 或等价 derived table：内层只读取筛选、别名聚合、排序和 cursor 所需窄列，先完成 `ORDER BY + LIMIT %s OFFSET %s`；外层再按候选 page ID join `wiki_pages` 取得 `content_json` 与更新时间，并按候选顺序返回。禁止通过增大全局 MySQL `sort_buffer_size` 掩盖查询结构问题，也不得改 canonical schema。

搜索优先级保持现有语义：exact title -> title contains -> exact alias -> alias contains -> subtitle -> source title -> page ID。无 `q` 时仍按 page ID 稳定排序。所有 DB 执行异常包装为 `WikiRepositoryUnavailable`，保留内部 cause 供日志诊断，但响应不得泄漏连接信息。

- [ ] **Step 4: 映射 cursor 与 repository 错误**

`backend/wiki.py` 只在 `/api/wiki/pages` 和 `/api/wiki/search` 的共用读取路径增加：

- `InvalidWikiCursor -> HTTP 400`，公开固定错误文案，不返回 payload 内容。
- `WikiRepositoryUnavailable -> HTTP 503`，公开“Wiki 数据暂不可用”，不返回 SQL、host、user 或密码。

不修改 `/health`、RAG `_state`、其他 router 或成功响应 schema。

- [ ] **Step 5: 扩展真实 Wiki verifier**

新增参数：

```text
--check-page-list
--page-list-type character
--search-probe TEXT   # 可重复
```

verifier 使用 Python HTTP 客户端按 JSON UTF-8 规范解码，不依赖 Windows PowerShell 5.1 对无 charset JSON 的错误推断。它读取 `/api/wiki/categories` 的实时 count，跟随每个 opaque cursor，断言 cursor 不循环、page ID 不重复、累计唯一数等于 count；每个 probe 断言精确标题存在且排在首项。

- [ ] **Step 6: 运行 repository、API 与 verifier 测试**

```powershell
python -m pytest tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py tests/test_huiji_wiki_e2e_script.py -q
```

Expected: PASS；旧漏项断言已被无损分页断言取代，空结果与服务错误可区分。

- [ ] **Step 7: 重启 8000 并执行真实 MySQL 读链路验收**

按项目既有方式重启 FastAPI 后运行：

```powershell
python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --check-page-list --page-list-type character --search-probe "J" --search-probe "6" --search-probe "露西" --inspection-label stitch-wiki-list --output eval/stitch-wiki-p0/wiki-page-list.json
```

Expected: exit `0`；当前 snapshot 的角色分类 count 为 132，遍历得到 132 个唯一 page ID；`J`、`6`、`露西` 均为各自搜索首项。若 snapshot 已变化，以实时 count 为准，但仍要求 count 与唯一遍历数相等。

### Task 4: Wiki 路由分类、历史状态与请求隔离

**对应 specs:** `SHELL-P0-01`、`SHELL-P0-05`、`SHELL-P0-07`、`INDEX-P0-04` 至 `INDEX-P0-06`、`BOUNDARY-P0-05`

**Files:**
- Create: `frontend/react-app/src/components/wiki/wikiRoutes.ts`
- Create: `frontend/react-app/src/components/wiki/wikiRoutes.test.ts`
- Create: `frontend/react-app/src/components/wiki/WikiErrorBoundary.tsx`
- Create: `frontend/react-app/src/components/wiki/WikiErrorBoundary.test.tsx`
- Modify: `frontend/react-app/src/App.tsx`
- Modify: `frontend/react-app/src/App.wiki.test.tsx`
- Modify: `frontend/react-app/src/api/wiki.ts`
- Modify: `frontend/react-app/src/api/wiki.test.ts`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.test.tsx`

**Interfaces:**

```ts
export type WikiLocation =
  | { kind: 'character-selection' }
  | { kind: 'detail'; route: string; resolverHint?: string }

export interface WikiSelectionHistoryState {
  category: string
  query: string
  selectedPageId: string
  listScrollTop: number
}

export function parseWikiLocation(pathname: string): WikiLocation
export function replaceWikiLocation(route: string, state?: unknown): void
export function pushWikiDetail(route: string, selection: WikiSelectionHistoryState): void
export function readWikiSelectionState(state: unknown): WikiSelectionHistoryState | null

export class WikiApiError extends Error {
  constructor(readonly status: number, readonly url: string) { super(`HTTP ${status}`) }
}
```

不得引入 React Router。`wikiRoutes.ts` 集中封装 `window.history.pushState/replaceState` 和 `popstate`；视觉组件不得直接写 `window.location`。

- [ ] **Step 1: 写路由与历史状态失败测试**

覆盖以下输入与结果：

```ts
expect(parseWikiLocation('/wiki')).toEqual({ kind: 'character-selection' })
expect(parseWikiLocation('/wiki/character')).toEqual({ kind: 'character-selection' })
expect(parseWikiLocation('/wiki/character/3003')).toEqual({ kind: 'detail', route: '/wiki/character/3003', resolverHint: '3003' })
expect(parseWikiLocation('/wiki/char/3003')).toEqual({ kind: 'detail', route: '/wiki/char/3003' })
expect(parseWikiLocation('/wiki/story/42')).toEqual({ kind: 'detail', route: '/wiki/story/42' })
```

另断言 `pushWikiDetail('/wiki/char/3003', selection)` 原样写入 API route 和选择状态；无效 history state 返回 `null`，不污染搜索条件；`fetchJson` 的 404 抛出 `WikiApiError(status=404)`，网络错误和 500 不会伪装成 404。

- [ ] **Step 2: 运行测试确认路由模块不存在**

```powershell
npx vitest run src/components/wiki/wikiRoutes.test.ts src/App.wiki.test.tsx src/api/wiki.test.ts
```

Expected: FAIL，当前 `/wiki/character` 会被当作详情 route，且 App 不监听 `popstate`。

- [ ] **Step 3: 实现 route 分类与别名归一**

`/wiki` 使用 `replaceState` 归一为 `/wiki/character`。除精确选人路径外，先对完整 pathname 调用 `fetchWikiPageByRoute(route)`；这一步可以直接接受历史 `/wiki/char/:id`，也可以接受 importer 生成的 `/wiki/character/:id`。只有捕获到 `WikiApiError` 且 `status === 404`、同时存在 `resolverHint` 时，才调用 `resolveWikiRoute({ entityId: hint })`；非数字 hint 在 entity 解析无结果后才以 `title` 再解析一次。resolver 返回 route 后 `replaceState` 并加载一次；不得在前端拼接或替换 route 前缀。API 返回的 `page.route` 是最终地址权威。

- [ ] **Step 4: 让 WikiShell 按 route 分离请求**

`WikiShell` 维护当前位置和三个独立失败域：

```ts
const [location, setLocation] = useState(() => parseWikiLocation(window.location.pathname))
const [categoryError, setCategoryError] = useState('')
const [listError, setListError] = useState('')
const [listCursor, setListCursor] = useState<string | null>(null)
const [listLoadingMore, setListLoadingMore] = useState(false)
const [previewError, setPreviewError] = useState('')
const [detailError, setDetailError] = useState('')
```

- 选人 route 请求 categories/pages；首批响应保存不透明 `nextCursor`，`loadMore` 在分类和查询未变化时追加并按 `pageId` 去重。分类/查询改变时立即丢弃 pages/cursor，旧请求即使晚到也不得写入新结果；条目变化可请求一份 detail 作为增强预览，但失败时保留 list item 级预览。
- page list 的 400/503/网络错误写入 `listError`，已有 pages 不清空；只有成功的 `items=[]` 且当前 pages 也为空时才显示真正空结果。
- 详情 route 先调用 `fetchWikiPageByRoute(route)`；不得先请求 page list，也不得自动选列表第一项。
- 只有深层详情直取返回 404 时才执行 resolver fallback；网络错误、500 或超时不得误判为 alias。
- 任何详情成功后都以响应里的 `page.route` 更新最近访问，展示组件只消费 Task 3 的 view model。

- [ ] **Step 5: 保存并恢复选人状态**

每次分类、查询、选中项或列表滚动变化时，用 `replaceState` 更新当前选人 entry；CTA 通过 `pushWikiDetail(selected.route, selectionState)` 进入详情。`popstate` 回到选人 entry 时恢复四个字段，并在列表渲染后恢复 `scrollTop`。直接打开详情且没有选人 history 时，“返回角色索引”使用 `/wiki/character`。

- [ ] **Step 6: 实现可重置局部错误边界**

```tsx
export class WikiErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidUpdate(previous: Props) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false })
  }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}
```

- [ ] **Step 7: 运行路由、Shell 与 API 回归测试**

```powershell
npx vitest run src/components/wiki/wikiRoutes.test.ts src/components/wiki/WikiShell.test.tsx src/components/wiki/WikiErrorBoundary.test.tsx src/App.wiki.test.tsx src/api/wiki.test.ts
```

Expected: PASS；API 规范 route 直达不发出 list 请求，resolver 只在直取 404 后触发，Back 恢复选人状态；cursor 追加无重复，筛选变化隔离旧请求，503 不会显示成空结果。

### Task 5: 独立选人页与角色详情页布局

**对应 specs:** `SHELL-P0-01` 至 `SHELL-P0-06`、`RAW-P0-08`

**Files:**
- Create: `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.tsx`
- Create: `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.css`
- Create: `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.test.tsx`
- Create: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.tsx`
- Create: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css`
- Create: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Delete: `frontend/react-app/src/components/wiki/wikiLayout.ts`

**Interfaces:**

```ts
export interface WikiCharacterSelectionPageProps {
  index: ReactNode
  preview: ReactNode
  summary: ReactNode
  canOpenDetail: boolean
  onOpenDetail(): void
}

export interface WikiCharacterDetailPageProps {
  profile: ReactNode
  skills: ReactNode
  mediaStage: ReactNode
  inheritance: ReactNode
  portray: ReactNode
  voices: ReactNode
  archive: ReactNode
  body: ReactNode
  onBack(): void
}
```

- [ ] **Step 1: 写双页面结构失败测试**

选人页断言只包含 `selection-index`、`selection-preview`、`selection-summary` 与“查看完整档案”，不包含完整正文、技能、语音或 `detail-layout`。详情页断言包含 `detail-profile`、`detail-skills`、`detail-media`、`detail-inheritance`、`detail-portray`、`detail-voices`、`detail-archive`、`detail-body` 与返回入口，不包含选人搜索和列表。

```tsx
expect(screen.getByTestId('wiki-character-selection')).toBeInTheDocument()
expect(screen.queryByTestId('wiki-character-detail')).not.toBeInTheDocument()
expect(screen.queryByTestId('wiki-structured-body')).not.toBeInTheDocument()
```

- [ ] **Step 2: 运行测试确认当前单壳体失败**

```powershell
npx vitest run src/components/wiki/WikiCharacterSelectionPage.test.tsx src/components/wiki/WikiCharacterDetailPage.test.tsx src/components/wiki/WikiShell.test.tsx
```

Expected: FAIL，当前 `WikiShell` 同时挂载 index、reader、info。

- [ ] **Step 3: 实现选人页布局**

对照 Stitch `分类选择界面` Desktop `60d1cf6aae8942a19cab0b0a298d2139` 与 Mobile `019774f3c2664e7a8d0fcb4a28d76119`：

- 宽屏使用紧凑索引、主预览、摘要/CTA 三个视觉区，主预览占比最大。
- 索引只负责搜索、数量和条目；预览使用选中角色大图或稳定占位。
- CTA 未选中或 route 缺失时禁用，不渲染完整详情正文。
- 移动端按“搜索/列表 -> 预览 -> CTA”自然纵向排列，不用 CSS 隐藏详情 DOM。

- [ ] **Step 4: 实现详情页布局**

对照 Stitch `个人详情` Desktop `a1f37efca7104637bf2a23ffe14196c2` 与 Mobile `446f20871c514bb6baafba2dab6613c6`：

- 宽屏为左侧资料/技能、中部大立绘、右侧传承/塑造/语音/档案三大区域；媒体区必须是最大单一视觉信号。
- 页面使用 document scroll；长正文继续排在首屏档案板下方。只有明确受视口约束的侧区允许 `overflow:auto`，不能锁死全局滚动。
- 中等宽度先保持媒体可辨认，再把资料与档案重排到媒体前后。
- 移动端使用单列档案流，返回入口始终可见，不复制桌面固定画布。

- [ ] **Step 5: 接入 WikiShell 并删除旧固定列常量**

`WikiShell` 根据 Task 4 的 `location.kind` 只挂载一个页面组件。移除内联响应式 `<style>`、`WIKI_LAYOUT_COLUMNS`、旧 `wiki-layout` 三栏 DOM 和移动 pane 状态。两页共享 `RouteAwareCardNav`，但各自拥有布局根节点和测试 ID。

- [ ] **Step 6: 运行布局与 Shell 测试**

```powershell
npx vitest run src/components/wiki/WikiCharacterSelectionPage.test.tsx src/components/wiki/WikiCharacterDetailPage.test.tsx src/components/wiki/WikiShell.test.tsx
```

Expected: PASS；任一 route 的 DOM 中都不会同时出现 selection 与 detail 根节点。

### Task 6: 选人页档案索引与预览选择

**对应 specs:** `INDEX-P0-01` 至 `INDEX-P0-06`

**Files:**
- Modify: `frontend/react-app/src/components/wiki/PageIndex.tsx`
- Modify: `frontend/react-app/src/components/wiki/PageIndex.css`
- Modify: `frontend/react-app/src/components/wiki/PageIndex.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterSelectionPage.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiShell.test.tsx`

**Interfaces:**

```ts
interface PageIndexProps {
  pages: WikiIndexItemViewModel[]
  selectedPageId: string
  query: string
  activeCategoryLabel: string
  loading: boolean
  loadingMore: boolean
  error: string
  loadedCount: number
  totalCount: number
  hasMore: boolean
  restoreScrollTop: number
  onQueryChange(query: string): void
  onSelect(pageId: string): void
  onScrollTopChange(scrollTop: number): void
  onLoadMore(): void
  onRetry(): void
}
```

- [ ] **Step 1: 写索引失败测试**

测试每个索引项只显示缩略图、名称和 `meta`，不显示完整 summary；同时覆盖缺图、loading、空结果、error+retry、选中、键盘焦点、`restoreScrollTop`、已加载/总数和 load-more。点击条目只调用 `onSelect`，不得调用 history 或挂载详情页；load-more 只调用 `onLoadMore`，加载中禁用，`hasMore=false` 时不显示。

```tsx
expect(screen.getByText('character · char:3074')).toBeInTheDocument()
expect(screen.queryByText('不应显示的长摘要')).not.toBeInTheDocument()
expect(screen.getByRole('button', { name: '重试条目列表' })).toBeEnabled()
expect(screen.getByText('已载入 30 / 132')).toBeInTheDocument()
expect(screen.getByRole('button', { name: '加载更多档案' })).toBeEnabled()
```

- [ ] **Step 2: 运行测试确认旧抽屉/同页详情结构失败**

```powershell
npx vitest run src/components/wiki/PageIndex.test.tsx
```

Expected: FAIL。

- [ ] **Step 3: 实现稳定索引结构**

移除移动抽屉和同页详情开关；现有 `AnimatedContent` 仅在不改变尺寸、滚动或 reduced-motion 契约时保留，不是本 Task 的新增验收项。条目按钮结构固定为：

```tsx
<button className="wiki-index-item" aria-pressed={selected} onClick={() => onSelect(page.pageId)}>
  <span className="wiki-index-item__media">
    {page.thumbnail ? <img src={page.thumbnail} alt="" loading="lazy" /> : <span data-testid="wiki-index-placeholder" />}
  </span>
  <strong>{page.title}</strong>
  <span className="archive-meta">{page.meta}</span>
</button>
```

错误状态不得替换搜索框；已有 `pages` 非空时仍展示旧列表，并在列表上方显示错误提示。列表容器恢复 `restoreScrollTop`，滚动时节流调用 `onScrollTopChange`，供 Task 4 写入当前 history entry。列表尾部显示 `loadedCount / totalCount`；`hasMore` 时提供带 `ChevronDown` 图标的“加载更多档案”按钮，按钮尺寸稳定且不引入自动滚动。`WikiShell` 负责 cursor、去重、过期请求隔离和 total count，`PageIndex` 不解析 cursor。

- [ ] **Step 4: 实现稳定尺寸和档案线框 CSS**

```css
.wiki-page-index { min-width: 0; padding: 18px; background: var(--archive-panel); border: 1px solid var(--archive-line); }
.wiki-index-list { display: grid; gap: 10px; }
.wiki-index-item { min-height: 148px; display: grid; grid-template-columns: 88px minmax(0, 1fr); grid-template-rows: auto auto; gap: 6px 12px; border: 1px solid transparent; }
.wiki-index-item__media { grid-row: 1 / 3; width: 88px; height: 116px; overflow: hidden; }
.wiki-index-item__media img { width: 100%; height: 100%; object-fit: contain; background: transparent; }
.wiki-index-item[aria-pressed='true'], .wiki-index-item:focus-visible { border-color: var(--accent-rust); background: color-mix(in srgb, var(--accent-rust) 8%, transparent); }
```

- [ ] **Step 5: 运行索引和 Shell 测试**

```powershell
npx vitest run src/components/wiki/PageIndex.test.tsx src/components/wiki/WikiShell.test.tsx
```

Expected: PASS；条目选择只更新预览，列表滚动状态可恢复，分页追加无漏项/重复，503 保留旧列表，索引不挂载完整详情 DOM。

### Task 7: 透明 WikiHeroStage 与初始/洞悉/Live2D 共用窗口

**对应 specs:** `MEDIA-STAGE-P0-01` 至 `MEDIA-STAGE-P0-07`、`MOTION-P0-02`、`MOTION-P0-03`

**Files:**
- Create: `frontend/react-app/src/components/wiki/WikiHeroStage.tsx`
- Create: `frontend/react-app/src/components/wiki/WikiHeroStage.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterMediaStage.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/StoryPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/PsychubePage.tsx`

**Interfaces:**

```ts
interface WikiHeroStageProps {
  title: string
  candidates: readonly WikiMediaViewModel[]
  emptyLabel: string
  activeIndex?: number
  onActiveIndexChange?(index: number): void
}
```

- [ ] **Step 1: 写媒体舞台失败测试**

覆盖：首张图片失败后切换下一候选、全部失败显示固定空态、舞台仍保留标题和正文兄弟节点、图片容器无 border/background、明确 initial/insight 可切换、未分类多立绘使用中性标签、角色 Live2D 按钮不可用但静态立绘保持显示、正常模式继续使用 `TiltedImageCard`。

```tsx
fireEvent.error(screen.getByRole('img', { name: '第一张' }))
expect(screen.getByRole('img', { name: '第二张' })).toBeInTheDocument()
expect(screen.getByRole('button', { name: 'Live2D（未就绪）' })).toHaveAttribute('aria-disabled', 'true')
expect(screen.getByRole('button', { name: '初始' })).toHaveAttribute('aria-pressed', 'true')
expect(screen.getByTestId('tilted-image-card')).toBeInTheDocument()
```

- [ ] **Step 2: 运行测试验证失败**

```powershell
npx vitest run src/components/wiki/WikiHeroStage.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx
```

Expected: FAIL。

- [ ] **Step 3: 实现通用透明舞台**

`WikiHeroStage` 维护失败 URL 集合，从 `candidates` 中选择首个未失败项；`onError` 只标记该 URL。核心 DOM：

```tsx
<figure className="wiki-hero-stage" data-testid="wiki-hero-stage">
  {active ? <TiltedImageCard src={active.url} alt={active.title || title} onImageError={() => markFailed(active.url)} /> : <div className="archive-empty">{emptyLabel}</div>}
</figure>
```

CSS 尺寸使用 `min-height: clamp(34rem, 72dvh, 58rem)`、`max-width: 100%`、`object-fit: contain`、透明背景、无边框。`TiltedImageCard` 继续遵守自身 reduced-motion 与触摸降级，舞台不得覆盖其交互或将其改写为静态 `<img>`。

- [ ] **Step 4: 重构 CharacterMediaStage**

组件改为接收 `WikiPageViewModel` 的 `portraitSlots`、`portraits` 和 `voices`。明确槽位显示“初始/洞悉”；只有未分类 portrait 时按稳定 API 数组顺序显示“立绘 1/立绘 2”，不得解析文件名重新排序或命名。Live2D 按钮显示 `aria-disabled="true"` 与可见“播放器未就绪”说明，静态 L2d 图片也不能被当作可播放 Live2D；点击/键盘不能清空当前立绘。切换只改变 active media，舞台尺寸不变；语音继续通过显式入口展开。

- [ ] **Step 5: 让剧情和心相复用 WikiHeroStage**

`WikiReaderHero` 在 story/psychube 分支中使用 `view.images` 渲染 `WikiHeroStage`；`StoryPage`、`PsychubePage` 只负责正文。无媒体时 hero slot 显示紧凑空态，不生成固定大空框。

- [ ] **Step 6: 运行媒体和模板测试**

```powershell
npx vitest run src/components/wiki/WikiHeroStage.test.tsx src/components/wiki/templates/CharacterMediaStage.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx
```

Expected: PASS；角色和通用舞台保留 `TiltedImageCard` 正常模式，媒体失败只影响当前候选。

### Task 8: 结构化正文、既有 Scroll Reveal 与 block 级错误边界

**对应 specs:** `CONTENT-P0-01` 至 `CONTENT-P0-08`、`RAW-P0-03`、`RAW-P0-06`、`RAW-P0-08`、`MOTION-P0-02`

**Files:**
- Modify: `frontend/react-app/src/components/wiki/StructuredContentRenderer.tsx`
- Modify: `frontend/react-app/src/components/wiki/StructuredContentRenderer.css`
- Modify: `frontend/react-app/src/components/wiki/StructuredContentRenderer.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiScrollRevealText.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiReader.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/CharacterPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/StoryPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/PsychubePage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/GenericWikiPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/templates/WikiTemplates.test.tsx`

**Interfaces:**
- Consumes: `WikiPageViewModel.blocks` 与 `fallbackText`。
- Produces: heading/facts/list/quote/table/structured/paragraph/voice_reference DOM；既有 `reveal` 标记继续通过 `WikiScrollRevealText` 渲染。

```ts
interface WikiReaderHeroProps { view: WikiPageViewModel | null; loading?: boolean; error?: string }
interface WikiReaderBodyProps { view: WikiPageViewModel | null; loading?: boolean; error?: string }
```

- [ ] **Step 1: 写正文失败测试**

增加以下断言：fallback 长文生成多个 `<p>`；未知/异常 block 显示局部“该段资料暂不可用”且后续段落继续；所有 matching link spans 可点击；raw/source 诊断对象不显示；`inheritance` 表保留可变洞悉行，`portray` 表保留 `LV.1..LV.5`；`reveal: true` 的 block 保留 `[data-reveal-word]`，`enabled: false` 或 reduced-motion 时文本仍完整可读。

```tsx
expect(container.querySelectorAll('p').length).toBeGreaterThan(1)
expect(screen.getByText('后续正文')).toBeInTheDocument()
expect(container.querySelectorAll('[data-reveal-word]').length).toBeGreaterThan(0)
```

- [ ] **Step 2: 运行测试确认 fallback/局部错误行为失败且记录既有 reveal 基线**

```powershell
npx vitest run src/components/wiki/StructuredContentRenderer.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx
```

Expected: FAIL。

- [ ] **Step 3: 保留 WikiScrollRevealText 的既有语义开关**

```tsx
export function WikiScrollRevealText({ text, enabled, as = 'p', pageType = '' }: Props) {
  const profile = getWikiMotionProfile(pageType)
  return <ScrollReveal text={text} scrollContainer={null} baseRotation={0} enabled={enabled} as={as} blurStrength={profile.revealBlur} revealStart={profile.revealStart} />
}
```

不改变现有 `reveal` 判定、GSAP 清理和 `getMotionPolicy()` 降级。只允许为新详情布局调整 className 或最近滚动容器解析；不得把所有正文强制设为 animated，也不得全局静态化。

- [ ] **Step 4: 每个 block 使用局部错误边界**

`StructuredContentRenderer` 对每个 block 渲染：

```tsx
<WikiErrorBoundary key={block.id} resetKey={block.id} fallback={<p className="archive-error">该段资料暂不可用</p>}>
  <Block block={block} pageType={pageType} linkSpans={matchingSpans} />
</WikiErrorBoundary>
```

未知 block type 返回紧凑局部错误；现有 `structured` 最大递归深度保持 3，不能渲染 `content.raw`。

- [ ] **Step 5: 重组 page type 模板**

`WikiReaderHero` 负责角色 `CharacterMediaStage` 或剧情/心相/通用 `WikiHeroStage`；`WikiReaderBody` 负责档案标题/副标题、blocks 正文、语音入口/关联内容和 page type 模板分流。角色详情按 Task 3 的 `characterSections` 填槽：`profile + skills` 进入左区，`inheritance + portray + voices + archive` 进入右区，`remainder` 与未在首屏完整展开的 archive blocks 进入下方正文。raw supplement 覆盖的角色若 inheritance/portray 为空，显示数据链路错误并使 P0 测试失败；只有未被 raw 覆盖的新角色才可无空卡跳过。其他规范详情 route 继续复用现有 page type 模板。模板不得再创建第二个固定高度媒体舞台或 `maxHeight: calc(100vh...)` 锁死 document scroll。

- [ ] **Step 6: 更新正文 CSS**

正文最大行宽使用 `72ch`；标题为衬线、元数据为等宽；段落 `line-height: 1.8`；事实字段在窄屏转单列；图片和表格不溢出。禁止给整个章节套浅色卡片。

- [ ] **Step 7: 运行正文、链接和模板测试**

```powershell
npx vitest run src/components/wiki/StructuredContentRenderer.test.tsx src/components/wiki/KeywordText.test.tsx src/components/wiki/templates/WikiTemplates.test.tsx src/components/wiki/WikiErrorBoundary.test.tsx
```

Expected: PASS。

### Task 9: 角色详情档案信息与稳定链接

**对应 specs:** `DOSSIER-P0-01` 至 `DOSSIER-P0-05`、`RAW-P0-03`、`RAW-P0-08`

**Files:**
- Modify: `frontend/react-app/src/components/wiki/PageInfo.tsx`
- Modify: `frontend/react-app/src/components/wiki/PageInfo.test.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.tsx`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css`
- Modify: `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.test.tsx`

**Interfaces:**
- Consumes: `WikiPageViewModel.profileFacts`、`WikiPageViewModel.dossier`、原始 `relations` 和已验证 route。
- Produces: Stitch 档案密度所需的角色事实、可复制技术字段、稳定 route 链接、可解析关系链接和缺失值显示。

```ts
interface PageInfoProps { view: WikiPageViewModel | null }
```

- [ ] **Step 1: 写档案栏失败测试**

```tsx
expect(screen.getByText('char:3074')).toBeInTheDocument()
expect(screen.getByText('角色')).toBeInTheDocument()
expect(screen.getByText('无')).toBeInTheDocument()
expect(screen.getByRole('link', { name: '/wiki/char/3074' })).toHaveAttribute('href', '/wiki/char/3074')
expect(screen.queryByText('undefined')).not.toBeInTheDocument()
expect(screen.getByText('介质')).toBeInTheDocument()
expect(screen.getByText('树木')).toBeInTheDocument()
expect(screen.getByText('木秀于林')).toBeInTheDocument()
```

关系对象只有在含 `targetRoute`/`route` 时渲染链接；否则只渲染 API 提供的标题文本，不猜 route。

- [ ] **Step 2: 运行测试确认当前字段不足**

```powershell
npx vitest run src/components/wiki/PageInfo.test.tsx
```

Expected: FAIL，当前缺少 Category、Type、Page ID、Aliases，且未消费 raw supplement profile。

- [ ] **Step 3: 使用视图模型渲染档案字段**

```tsx
<dl className="wiki-dossier-info__fields">
  {view.dossier.map((field) => (
    <div key={field.label}>
      <dt>{field.label}</dt>
      <dd>{field.href ? <a href={field.href}>{field.value}</a> : field.value}</dd>
    </div>
  ))}
</dl>
```

`WikiCharacterDetailPage` 在 profile/skills 区先渲染 `profileFacts`，再渲染技能；`PageInfo` 渲染 Source/Route 等技术 dossier。传承名称可作为 profile fact，但完整洞悉效果仍来自 inheritance blocks；定位标签和香调用可换行文本/标签组，不生成嵌套卡片。`id="wiki-info"` 保留；文本必须可选择和 `overflow-wrap:anywhere`。

- [ ] **Step 4: 完成独立滚动和链接视觉**

滚动由 `WikiCharacterDetailPage.css` 的 archive 区控制；`PageInfo` 自身不写固定 `100vh` inline height。桌面 archive 区只有在实际受视口约束且内容溢出时独立滚动，移动端回到 document flow。内部链接使用 `--link-accent`，`:focus-visible` 清楚可见。

- [ ] **Step 5: 运行档案栏和布局测试**

```powershell
npx vitest run src/components/wiki/PageInfo.test.tsx src/components/wiki/WikiCharacterDetailPage.test.tsx
```

Expected: PASS。

### Task 10: 既有动效非回归与主站视觉继承

**对应 specs:** `MAIN-P0-01` 至 `MAIN-P0-03`、`MOTION-P0-01` 至 `MOTION-P0-03`

**Files:**
- Verify: `frontend/react-app/src/components/ui/TiltedImageCard.tsx`
- Verify: `frontend/react-app/src/components/wiki/WikiScrollRevealText.tsx`
- Verify: `frontend/react-app/src/components/chat/AnimatedVoiceList.tsx`
- Create: `frontend/react-app/src/components/chat/AnimatedVoiceList.test.tsx`
- Verify: `frontend/react-app/src/components/chat/CircularMediaGallery.tsx`
- Create: `frontend/react-app/src/components/chat/CircularMediaGallery.test.tsx`
- Modify: `frontend/react-app/src/components/sections/HomeSection.test.tsx`
- Modify: `frontend/react-app/src/components/sections/ChatSection.test.tsx`
- Modify: `frontend/react-app/src/components/sections/CategoryPanel.test.tsx`
- Modify: `frontend/react-app/src/styles/global.css`

**Interfaces:**
- `TiltedImageCard` 保持当前 `src/alt/containerStyle/imageStyle/onImageError` 接口和正常模式倾斜/缩放行为。
- `AnimatedVoiceList` 保持 `lines/renderLine` 接口并继续委托 `AnimatedList`。
- `CircularMediaGallery` 保持 `items` 接口并继续委托 `CircularGallery`，WebGL/能力不足时使用完整 DOM fallback。
- `WikiScrollRevealText` 保持 `text/enabled/as/pageType` 接口并继续委托 `ScrollReveal`。

- [ ] **Step 1: 写既有行为保护测试**

```tsx
render(<AnimatedVoiceList lines={lines} renderLine={(line) => <button>{line.title}</button>} />)
expect(screen.getByRole('listbox', { name: 'Voice lines' })).toHaveClass('reactbits-animated-list')
expect(screen.getAllByRole('option')).toHaveLength(lines.length)

render(<CircularMediaGallery items={images} />)
expect(container.querySelector('.circular-gallery')).toBeInTheDocument()
```

补充断言：Animated List Arrow/Enter 仍可操作；Circular Gallery 在 mock WebGL 失败或 motion policy 禁用时完整 fallback 仍包含所有图片和 viewer；`TiltedImageCard` 正常模式仍响应非触摸 pointer，reduced-motion/触摸不旋转；`WikiScrollRevealText enabled` 仍生成 reveal word，禁用时文本仍可读。

- [ ] **Step 2: 先运行保护测试记录基线**

```powershell
npx vitest run src/components/chat/AnimatedVoiceList.test.tsx src/components/chat/CircularMediaGallery.test.tsx src/components/animations/reactbits/ReactBitsAdapters.test.tsx src/components/animations/reactbits/CircularGallery.test.tsx src/components/sections/CategoryPanel.test.tsx
```

Expected: 新增测试可能因缺少 test setup 而先 FAIL；现有 ReactBits 测试必须保持 PASS。若现有测试先失败，先调查环境或既有回归，不能通过静态化组件让测试变绿。

- [ ] **Step 3: 只修复布局重构引入的动效回归**

默认不修改四个实现文件。只有测试证明新 CSS、滚动容器或新调用点破坏既有行为时，才做最小修复；不得增加“默认静态”分支，不得删除 Canvas/GSAP/Framer Motion，不得改变 `VoicePanel` 的语言切换、播放协调、分页、重试或 cursor 行为。

- [ ] **Step 4: 补充 Home/Chat/Data 回归断言**

- Home：视频 poster 仍为 `/images/global-background.png`，`canPlay` 后 opacity 从 `0` 到 `1`。
- Chat：空态、CategorySelect、返回首页、消息滚动容器仍存在。
- Data：分类数据与日历 `进入WIKI` 链接仍存在，封面 `TiltedImageCard` 的正常/降级行为和尺寸不变。
- 三页：外层背景来自语义令牌/全局背景，无旧浅色固定填充。

- [ ] **Step 5: 运行主站、媒体和动效回归测试**

```powershell
npx vitest run src/components/chat/AnimatedVoiceList.test.tsx src/components/chat/CircularMediaGallery.test.tsx src/components/animations/reactbits/ReactBitsAdapters.test.tsx src/components/animations/reactbits/CircularGallery.test.tsx src/components/sections/HomeSection.test.tsx src/components/sections/ChatSection.test.tsx src/components/sections/CategoryPanel.test.tsx src/components/chat/MessageBubble.test.tsx src/store/chatStore.test.ts
```

Expected: PASS；正常模式保留现有动效，reduced-motion/能力不足时内容完整可达，Card Nav 测试仍证明导航动画可用。

### Task 11: Playwright 真实链路、只读边界与最终硬门槛

**对应 specs:** 全部 P0，重点 `RAW-P0-01` 至 `RAW-P0-08`、`BOUNDARY-P0-01` 至 `BOUNDARY-P0-06`

**Files:**
- Create: `frontend/react-app/e2e/wiki-archival.spec.ts`
- Modify: `frontend/react-app/playwright.config.ts`
- Modify: `frontend/react-app/e2e/wiki-reactbits.spec.ts`
- Generate: `eval/stitch-wiki-p0/final-wiki.json`
- Generate: `eval/stitch-wiki-p0/playwright-report.json`
- Generate: `eval/stitch-wiki-p0/screenshots/*.png`
- Generate: `eval/stitch-wiki-p0/forbidden-files.after.sha256`

**Interfaces:**
- Consumes: 真实 `data/raw` digest、`:8000`、项目 MySQL canonical + supplement、MinIO HTTP 资源、Vite `:5173`。
- Produces: 可审查的 enrichment receipt、测试报告、截图、网络审计、canonical 不变证明和双 snapshot 对比。

- [ ] **Step 1: 写双页面 E2E 并保留旧动效验收**

`wiki-archival.spec.ts` 至少包含以下独立测试：

1. `/wiki` 通过 `replaceState` 归一到 `/wiki/character`；选人根节点可见，详情根节点和完整正文不存在。
2. 选中角色只更新预览；“查看完整档案”的目标等于 list API 返回的 `page.route`，点击后进入规范 route，不拼接别名。
3. 在选人页设置分类、查询、选中项并滚动列表，进入详情后调用浏览器 Back，四项状态全部恢复。
4. 使用 `baseline-character.json` 记录的实际规范 route 直达：拦截 pages list 为失败时详情仍可显示，Network 中不出现依赖 list 后才取 detail 的顺序。
5. 深层 `/wiki/character/:slug`：若 `by-route` 成功则不得调用 resolver；若 mock 为 404 才经过 `/api/wiki/routes/resolve` 归一到响应 route；500/网络错误或 resolver 无结果时显示局部错误，不猜地址。
6. 详情桌面布局：profile/skills、media、inheritance、portray、archive/body 均存在，media 是最大视觉区；选人搜索/列表不存在。
7. 真实补全内容：槲寄生详情显示“木秀于林”、至少一个洞悉效果和 `LV.1..LV.5`；API `supplementSections` 含 inheritance/portray，页面 DOM 不出现 source key、raw 路径或原始 Markdown 图片目标。
8. 真实图片：选人缩略图、预览和详情主舞台 `naturalWidth > 0`，舞台透明无旧浅色卡框；有明确初始/洞悉映射时切换图片，不明确时显示中性标签；Live2D 未就绪不会清空静态图。
9. 响应式：两页在 2560、1440、1280、900、390 宽度都无重叠、裁切或失控横向滚动；移动端是自然单列和真实 route 流程。
10. 滚动：两页 document 可滚；详情受限侧区超长时可滚；移动端无锁死嵌套滚动。
11. 分类和主题：动态分类、`WIKI/首页`、键盘、Escape、三主题保持可用；非角色规范详情 route 继续进入已有模板。
12. 只读网络：所有 `/api/wiki/` 请求方法均为 `GET`；不存在 `:8001`、`file://`、磁盘路径、MinIO `PUT/POST/DELETE`。
13. Home/Chat/Data：三屏可进入，首页视频兜底存在，问答输入和资料日历入口可用。
14. reduced motion：Card Nav、Scroll Reveal、Tilted Card、Animated List、Circular Gallery 功能完整且按既有策略降级；正常模式仍由 `wiki-reactbits.spec.ts` 验收动效/WebGL/fallback。
15. page list：连续触发“加载更多档案”直到按钮消失，唯一条目数等于角色分类 count 且无重复；搜索 `J`、`6`、`露西` 时精确标题为首项，模拟 503 时保留已加载条目并显示重试而非空态。

两个页面分别使用真实 bounding box 验证主视觉占比：

```ts
const index = await page.getByTestId('selection-index').boundingBox()
const preview = await page.getByTestId('selection-preview').boundingBox()
const detailMedia = await page.getByTestId('detail-media').boundingBox()
const detailProfile = await page.getByTestId('detail-profile').boundingBox()
expect(preview!.width).toBeGreaterThan(index!.width)
expect(detailMedia!.width).toBeGreaterThan(detailProfile!.width)
```

只读网络审计：

```ts
const writes: string[] = []
page.on('request', (request) => {
  const url = request.url()
  if (url.includes('/api/wiki/') && request.method() !== 'GET') writes.push(`${request.method()} ${url}`)
  if (/:(8001)\b/.test(url) || /^(file:)|[A-Z]:\\/i.test(url)) writes.push(url)
  if (url.includes(':9002') && ['PUT', 'POST', 'DELETE', 'PATCH'].includes(request.method())) writes.push(`${request.method()} ${url}`)
})
// ...interactions...
expect(writes).toEqual([])
```

- [ ] **Step 2: 更新 Playwright 视口与报告目录**

保留现有 `desktop`、`narrow`、`mobile`、`reduced-motion`、`webgl-fallback` 项目，并增加两套 Stitch 专用桌面视口；不得删除 `webgl-fallback`：

```ts
projects: [
  { name: 'stitch-wide', use: { ...devices['Desktop Chrome'], viewport: { width: 2560, height: 1440 } } },
  { name: 'stitch-desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 1024 } } },
  { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  { name: 'narrow', use: { ...devices['Desktop Chrome'], viewport: { width: 900, height: 900 } } },
  { name: 'mobile', use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } } },
  { name: 'reduced-motion', use: { ...devices['Desktop Chrome'], viewport: { width: 1200, height: 900 }, reducedMotion: 'reduce' } },
  { name: 'webgl-fallback', use: { ...devices['Desktop Chrome'], viewport: { width: 1200, height: 900 } } },
]
```

JSON reporter 输出改为 `../../eval/stitch-wiki-p0/playwright-report.json`。

- [ ] **Step 3: 启动或确认本地服务**

后端使用现有稳定 `:8000`。另开终端启动前端：

```powershell
Set-Location D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run dev -- --host 127.0.0.1 --port 5173
```

Expected: `http://127.0.0.1:5173/`、`/wiki/character` 和一条真实规范详情 route 可访问。若端口占用，先确认占用者是否为本项目 Vite；不得盲目终止其他进程。

- [ ] **Step 4: 运行全部前端单测和生产构建**

```powershell
Set-Location D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm test
npm run build
```

Expected: 全部 PASS，TypeScript 和 Vite build exit `0`。

- [ ] **Step 5: 运行后端 Wiki/RAG 边界回归**

```powershell
Set-Location D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_raw_character_enrichment.py tests/test_huiji_wiki_supplement_migration.py tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_e2e_script.py tests/test_sse.py -q
```

Expected: PASS；supplement merge/health 通过，Wiki API 不触发 RAG 状态，SSE 契约不回归。

- [ ] **Step 6: 运行真实只读 Wiki 检查和 RAG smoke**

```powershell
python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --limit 30 --check-media --media-sample-limit 5 --check-page-list --page-list-type character --search-probe "J" --search-probe "6" --search-probe "露西" --require-supplement --expected-supplement-pages 104 --sample-title "槲寄生" --inspection-label stitch-wiki-after --output eval/stitch-wiki-p0/final-wiki.json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ask" -ContentType "application/json" -Body '{"question":"介绍一下十四行诗","category":null}'
```

Expected: verifier exit `0`，supplement ready/stale/count、槲寄生 inheritance/portray、HTTP media、local path leak、角色分页唯一数和三个短词搜索均通过；RAG 响应非空且无服务错误。

- [ ] **Step 7: 运行全部 Playwright 项目**

```powershell
Set-Location frontend/react-app
npm run test:e2e
```

Expected: 所有项目 PASS；输出选人页与详情页 Desktop/Mobile 全页截图；既有 Gallery Canvas 像素检查、拖动检查和强制 WebGL fallback 继续通过。

- [ ] **Step 8: 对比前后 snapshot receipt**

```powershell
Set-Location D:\PycharmProjects\nlp\LangChain\1999Search
$before = (Get-Content -Raw eval/stitch-wiki-p0/baseline-wiki.json | ConvertFrom-Json).health
$after = (Get-Content -Raw eval/stitch-wiki-p0/final-wiki.json | ConvertFrom-Json).health
foreach ($name in 'buildVersion','activationEpoch','manifestSha256Prefix') {
  if ($before.$name -ne $after.$name) { throw "Wiki snapshot changed: $name" }
}
$raw = Get-Content -Raw eval/stitch-wiki-p0/baseline-raw-character.json | ConvertFrom-Json
$apply = Get-Content -Raw eval/stitch-wiki-p0/raw-character-apply.json | ConvertFrom-Json
if ($raw.sourceRootDigest -ne $apply.sourceRootDigest) { throw 'Raw source snapshot changed' }
if (-not $after.supplementReady -or $after.supplementStale) { throw 'Wiki supplement is not current' }
```

Expected: 无输出、exit `0`。processed snapshot 与 raw source snapshot 任一变化都将验收标记 stale，必须重新执行 Task 0、Task 3A 和 Task 11，不混合结果。

- [ ] **Step 9: 对比禁止修改文件哈希**

```powershell
Get-FileHash backend/main.py,src/huiji_wiki/importer.py,src/huiji_wiki/content_blocks.py,src/rag/vectorstore.py,data/processed/huiji/dev/parent_blocks.jsonl,data/processed/huiji/dev/child_blocks.jsonl,data/processed/huiji/dev/media_assets.jsonl -Algorithm SHA256 | ConvertTo-Json | Set-Content -Encoding UTF8 eval/stitch-wiki-p0/forbidden-files.after.sha256
$before = Get-Content -Raw eval/stitch-wiki-p0/forbidden-files.before.sha256 | ConvertFrom-Json
$after = Get-Content -Raw eval/stitch-wiki-p0/forbidden-files.after.sha256 | ConvertFrom-Json
$diff = Compare-Object ($before | Sort-Object Path) ($after | Sort-Object Path) -Property Path,Hash
if ($diff) { $diff | Format-Table; throw 'Forbidden boundary files changed' }
```

Expected: 无差异。

- [ ] **Step 10: 对比 canonical MySQL 与 enrichment 幂等回执**

```powershell
$before = Get-Content -Raw eval/stitch-wiki-p0/canonical-mysql.before.json | ConvertFrom-Json
$after = Get-Content -Raw eval/stitch-wiki-p0/canonical-mysql.after.json | ConvertFrom-Json
if ($before.digest -ne $after.digest) { throw 'Canonical Wiki MySQL changed' }
$second = Get-Content -Raw eval/stitch-wiki-p0/raw-character-second-apply.json | ConvertFrom-Json
if ($second.inserted -ne 0 -or $second.updated -ne 0 -or $second.unchanged -ne 104) { throw 'Supplement apply is not idempotent' }
```

Expected: canonical 表摘要完全一致；第二次 apply 为 104 个 unchanged。

- [ ] **Step 11: 人工对照 Stitch 画板**

逐张检查 `stitch-wide`、`stitch-desktop`、`desktop`、`mobile` 的选人页与详情页截图：

- 颜色、衬线标题、等宽元数据和铜色线框符合 Archival Noir。
- 选人页对照 Stitch `分类选择界面`：索引紧凑、预览最大、CTA 明确，未混入完整详情正文。
- 详情页对照 Stitch `个人详情`：左资料/技能、中部大立绘、右传承/塑造/档案/语音的层级清楚，扩展正文沿页面向下；传承和塑造来自真实 API，不是静态示例。
- 角色主立绘足够大且主体完整，透明舞台无旧浅色框；初始/洞悉或中性立绘标签不伪造数据语义。
- 1280、900 和移动端无重叠、裁切、不可达内容或失控横向滚动。
- 浏览器 Back 恢复选人状态，规范 route 与别名行为符合 Task 4。
- 首页、问答页、资料页已继承视觉基础，但布局和核心行为未被 P0 重写。

任何一项失败都回到对应 Task 修复并重跑该 Task 及 Task 11，不以“接近设计稿”豁免。

## 3. P1 可选后续子项目

以下项目不进入本计划主线。只有全部 P0 门槛通过且用户再次批准后，分别创建独立 implementation plan：

1. `VISUAL-P1-01` 至 `VISUAL-P1-02`：中性/亮色主题精修与页面级版式令牌。
2. `NAV-P1-01` 至 `NAV-P1-02`：页面二级入口、最近访问和实体内锚点。
3. `SHELL-P1-01` 至 `SHELL-P1-02`：page type 密度和用户折叠记忆。
4. `INDEX-P1-01` 至 `INDEX-P1-02`：结构化排序筛选和分类专属索引。
5. `MEDIA-STAGE-P1-01` 至 `MEDIA-STAGE-P1-02`：分类专属媒体策略与更多命名皮肤/版本映射。
6. `DOSSIER-P1-01` 至 `DOSSIER-P1-02`：目录、关系分组与 RAG 来源跳转。
7. `CONTENT-P1-01` 至 `CONTENT-P1-02`、`ADAPTER-P1-01` 至 `ADAPTER-P1-02`：更多 page type 模板和 block schema。
8. `MAIN-P1-01`：首页 Stitch 档案序章布局重构。
9. `MAIN-P1-02`：问答页档案终端布局重构。
10. `MAIN-P1-03`：资料页档案索引/时间记录布局重构。
11. `MOTION-P1-01`：仅在稳定布局上进行隔离动效试验。
12. `BOUNDARY-P1-01` 至 `BOUNDARY-P1-02`：RAG 来源跳转和媒体覆盖报告。
13. `RAW-P1-01` 至 `RAW-P1-02`：为心相、剧情、世界、阵营、日历建立各自 typed enrichment，并在有证据时补充媒体角色映射。

## 4. Deferred / Out of Scope

- 所有 `*-P2-*` 条目：可调视觉密度、命令面板、可拖拽分栏、虚拟列表、正式 Live2D、关系图谱、schema 迁移、复杂 ReactBits 动效、完整统一资源中心。
- 除带默认值的 supplement health 字段外，不做破坏性后端 API schema 扩展。
- canonical MySQL 导入、既有 Wiki importer 重跑、MinIO 上传/迁移、Milvus 或 RAG 重建；本轮仅执行 Task 3A 明确限定的 supplement migration/apply。
- 首页、问答页、资料页 P1 布局施工。

## 5. 完成后自检表

- [ ] `VISUAL-P0-01..08`：三主题、字体、背景、共享原语和自然滚动全部通过。
- [ ] `NAV-P0-01..06`：唯一 Card Nav、动态分类、主题和键盘/reduced-motion 全部通过。
- [ ] `SHELL-P0-01..07`：独立选人页/详情页、响应式重排、Back 恢复和错误空态全部通过。
- [ ] `INDEX-P0-01..06`：精简索引、预览选择、无损 cursor、短词搜索、API route CTA、失败保留和状态恢复全部通过。
- [ ] `MEDIA-STAGE-P0-01..07`：大立绘、透明舞台、初始/洞悉或中性标签、Live2D 不可用状态、媒体 fallback 和 HTTP URL 全部通过。
- [ ] `RAW-P0-01..08`：104 个 raw 角色 inventory、结构化 parser、精确匹配、独立 SQL、canonical 优先、事务/幂等、API 合并和真实槲寄生验收全部通过。
- [ ] `DOSSIER-P0-01..05`：所有字段、链接、换行、独立滚动和稳定 route 全部通过。
- [ ] `CONTENT-P0-01..08`：blocks、fallback、模板、链接、局部错误和响应式正文全部通过。
- [ ] `ADAPTER-P0-01..04`：纯函数、集中 fallback、inheritance/portray 分组、输入不变和兼容 API 契约全部通过。
- [ ] `MAIN-P0-01..03`：Home/Chat/Data 视觉继承且核心行为无回归。
- [ ] `MOTION-P0-01..03`：既有 Card Nav、Scroll Reveal、Tilted Card、Animated List、Circular Gallery 正常模式与降级行为均无回归。
- [ ] `BOUNDARY-P0-01..06`：`:8000`、RAG、Milvus、processed/raw 双 snapshot、canonical MySQL、MinIO 只读边界全部通过。
- [ ] enrichment/repository/API pytest、`npm test`、`npm run build`、后端回归、真实 Wiki verifier、RAG smoke、全部 Playwright 项目均 exit `0`。
- [ ] processed/raw snapshot receipt、`wiki-page-list.json` 的 count/unique/search probes、canonical MySQL digest 和禁止文件哈希全部符合预期；第二次 supplement apply 为 no-op。
- [ ] Stitch `分类选择界面` 与 `个人详情` 各自的 Desktop/Mobile 截图人工审查通过。
- [ ] P1 未执行项明确保留为后续子项目；P2 未进入施工。
