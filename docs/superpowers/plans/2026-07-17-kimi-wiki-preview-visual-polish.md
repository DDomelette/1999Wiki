# Kimi Wiki 预览视觉修订实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. 用户已选择当前会话内联执行，允许 Kimi CLI 辅助前端修改，不使用子代理调度。步骤使用 checkbox（`- [x]`）跟踪。

**Goal:** 修复 Wiki 预览页截图审查发现的顶栏、头像、简介、字号、左侧工具区和 Udimo 越界问题，同时保持真实 API、媒体安全边界和正式 `/wiki/*` 不变。

**Architecture:** 大头像在补充数据构建层通过资源 manifest 映射为 `roster_avatar`，由列表 API 作为 `thumbnail` 输出；前端 ViewModel 负责结构化 summary，React 组件只渲染公开 DTO。视觉修订全部限制在 `wiki-preview` 命名空间，Card Nav 仍保留点击展开菜单行为。

**Tech Stack:** Python 3、pytest、MySQL Wiki repository、MinIO supplement prefix、React 18、TypeScript、Vitest、Playwright、CSS。

## 全局约束

- 不修改 RAG `_state`、Milvus、`media_assets.jsonl` 或正式 `/wiki/*` 路由归属。
- 不在 React 中拼接头像文件名、object key、本地路径或 MinIO 内部地址。
- MinIO 只允许校验后写入新的 Wiki supplement avatar 对象，不覆盖或删除对象。
- 所有行为修改遵循 RED -> GREEN -> REFACTOR；Plan 是硬性验收门槛。
- 不执行 Git 提交。

---

### Task 1：大头像媒体契约

**Files:**
- Modify: `src/huiji_wiki/raw_character_enrichment.py`
- Modify: `src/huiji_wiki/repository.py`
- Create: `scripts/import_wiki_roster_avatars.py`
- Modify: `tests/test_huiji_wiki_character_visual_supplement.py`
- Modify: `tests/test_huiji_wiki_repository.py`
- Create: `tests/test_import_wiki_roster_avatars.py`
- Create/Update: `eval/kimi-wiki-preview-20260717/roster-avatar-*.json`

**Interfaces:**
- Produces: supplement media role `roster_avatar` and list `thumbnail` priority `roster_avatar -> portrait/image fallback`.

- [x] **Step 1:** 添加失败测试：manifest 中资源名只要以大小写不敏感、词序无关的方式同时包含 `headicon`、`large` 和 `{entity_id}01`，即可生成 `roster_avatar`；PNG/WebP 并存时优先 WebP，并校验 SHA-1、尺寸和隔离 object key。
- [x] **Step 2:** 运行目标 pytest，确认因缺少 avatar 映射而失败。
- [x] **Step 3:** 实现受控 avatar 资源解析、计划项和 supplement media link；保留 dry-run/apply 边界。
- [x] **Step 4:** 添加并运行 repository 失败测试，确认列表缩略图优先 `roster_avatar`。
- [x] **Step 5:** 实现批量缩略图查询优先级并运行目标测试至通过。
- [x] **Step 6:** 仅在 dry-run 证据正确后执行受控补充媒体构建/上传和 supplement 数据更新，核对 API `thumbnail` 为公开 HTTP URL。

### Task 2：结构化 PERSONNEL PREVIEW

**Files:**
- Modify: `frontend/react-app/src/components/wiki-preview/kimiWikiPreviewViewModel.ts`
- Modify: `frontend/react-app/src/components/wiki-preview/kimiWikiPreviewViewModel.test.ts`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterSelectionPage.tsx`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterSelectionPage.test.tsx`

**Interfaces:**
- Produces: `summaryFacts: Array<{label: string; value: string}>` and `summaryParagraphs: string[]` on selection entries.

- [x] **Step 1:** 添加失败测试，锁定事实行、空行分段、重复标题剔除和无结构 summary fallback。
- [x] **Step 2:** 运行 Vitest，确认 ViewModel/组件因缺少结构化输出失败。
- [x] **Step 3:** 实现纯函数 summary 解析和事实/段落 DOM，保持 API 输入不变。
- [x] **Step 4:** 运行目标测试至通过。

### Task 3：顶栏、详情字号、sticky 工具区和 Udimo 边界

**Files:**
- Modify: `frontend/react-app/src/components/wiki-preview/KimiDesktopCharacterDossier.tsx`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiPreview.css`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiPreviewCss.test.ts`
- Modify: `frontend/react-app/src/components/wiki-preview/KimiWikiCharacterDetailPage.test.tsx`

**Interfaces:**
- Produces: full-width persistent Card Nav, click-only menu, 8%-12% larger detail typography, sticky utility, bounded Udimo media.

- [x] **Step 1:** 添加失败测试，检查 utility 位于左列、CSS 含 full-width nav/shadow、sticky bottom、Udimo `max-width: 100%` 和放大后的正文规则。
- [x] **Step 2:** 运行目标 Vitest，确认新断言按预期失败。
- [x] **Step 3:** 移动 utility DOM 到左列末尾并实现 scoped CSS；不修改共享 Card Nav 的展开状态机。
- [x] **Step 4:** 运行目标测试至通过。

### Task 4：真实 API 与截图验收

**Files:**
- Modify: `frontend/react-app/e2e/wiki-kimi-preview.spec.ts`
- Create/Update: `eval/kimi-wiki-preview-20260717/polish-screenshots/*.png`
- Modify: `docs/superpowers/plans/2026-07-17-kimi-wiki-preview-visual-polish.md`

**Interfaces:**
- Consumes: real `http://127.0.0.1:8000/api/wiki/*` and public media URLs.

- [x] **Step 1:** 添加 E2E 断言：顶栏贴边且滚动后常驻、菜单默认关闭/点击展开、槲寄生大头像可解码、summary 分块、Udimo 不越过右列、utility 始终可见。
- [x] **Step 2:** 运行 E2E 并确认旧实现失败或新回归被捕获。
- [x] **Step 3:** 在 `1920x1080`、`1280x951`、`390x844` 生成选人/详情截图并人工对照用户标注。
- [x] **Step 4:** 运行 `npm test`、`npm run build`、目标 pytest、生产禁出字段扫描和 Wiki health 检查。
- [x] **Step 5:** 所有检查通过后勾选本 Plan；任何检查失败都不得宣称完成或切换正式 `/wiki/*`。

## 执行证据（2026-07-18）

- 后端目标回归：`58 passed`。
- 前端全量回归：`48` 个测试文件、`222 passed`。
- 生产构建：TypeScript 与 Vite 构建成功，`2330` 个模块完成转换；保留一个非阻断的 `541.89 kB` 分块体积警告。
- 真实浏览器 E2E：`wiki-kimi-preview.spec.ts` 的真实 Wiki API 用例 `1 passed`。
- 真实数据：Wiki health 为 ready，页面数 `7456`，supplement ready；RAG health 为 `ok`，`doc_count=16010`。
- 头像导入：`104` 个源页面中映射并更新 `103` 个；唯一缺失项为测试占位 `char:9999`；规范数据导入前后 SHA-256 摘要均为 `ad44a1515bd7c6da5b76c3c67643d3fc134f1194e747d6ef8fab0c31aa434302`。
- 媒体实测：`char:3003` 的 `thumbnail` 为公开 HTTP WebP，HEAD 返回 `200 image/webp`。
- 截图：选人页与详情页分别具备真实 `1920x1080`、`1280x951`、`390x844` 三组视口证据。
- 生产禁出字段扫描：未发现后端专用字段、本地绝对路径、`file://`、`:8001` 或 MinIO 内部 `:9000` 地址。
- 本任务未执行重新向量化、Milvus 写入或 collection 切换；若后续需要重新向量化，必须交由用户执行。
