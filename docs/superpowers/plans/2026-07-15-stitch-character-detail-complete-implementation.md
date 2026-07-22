# Stitch 角色详情页完整复刻实施 Plan

> 日期：2026-07-15  
> 对应规格：`docs/superpowers/specs/2026-07-13-stitch-archival-wiki-global-redesign.md`，重点为 6.8、6.9 节  
> 执行方式：当前工作区单线程执行，不生成子代理，不创建 worktree，不依赖 Git 提交作为恢复点  
> 硬门槛：本 Plan 的 CP-01 至 CP-10 是执行、复核和最终验收清单；任何 P0 检查点未通过都不得宣称完成

## 1. 目标

以已批准的 PC 详情截图和移动端九张连续截图为视觉权威，使用原生 React、响应式 CSS、真实 Wiki API、项目 MySQL 与共享 MinIO 完整重建角色详情页。页面必须包含真实身份资料、Initial/Insight 同舞台切换、传承、LV.1-LV.5 塑造、三张技能、语音、文化、六件藏品和技术页脚，不再使用通用 Grid/长文本近似 Stitch。

## 2. 架构

```text
data/raw 角色 Markdown（只读）
  + resources_manifest.jsonl（只读）
  + assets/files（只读、SHA-1 校验）
        |
        v
enrich_wiki_from_raw.py 统一构建器
  - 解析 profile / inheritance / portray / culture / collection
  - 以 page entity ID + collection ordinal 解析 Belonging 资源
  - 生成 Wiki supplement blocks + supplement media links
        |
        +--> 共享 MinIO：仅增加 wiki-supplement 前缀对象
        |
        +--> 项目 MySQL：wiki_page_supplements.media_links_json
                          |
                          v
FastAPI :8000 /api/wiki/*（只读）
  - canonical + supplement 合并
  - URL 与安全媒体字段白名单
                          |
                          v
wikiCharacterDetailViewModel（纯函数）
  - profile / summary / portraits / skills / inheritance / portray
  - voices / culture / collections / technical dossier
                          |
                          v
DesktopCharacterDossier / MobileCharacterDossier
  - 同一数据模型，不共享错误的桌面缩放 DOM
  - Card Nav 保留
```

## 3. 不可突破的边界

1. 不修改 `data/processed/huiji/dev/*.jsonl`，不修改 `media_assets.jsonl`。
2. 不读写 Milvus，不切换 collection，不触发 RAG `_state`，不改 `/ask`、SSE 或 RAG 检索链路。
3. 不扫描 MinIO 推断页面资源；资源选择只来自 raw、resources manifest 与构建器的确定映射。
4. MinIO 只允许增加 `reverse1999/wiki-supplement/character/**` 对象；不得覆盖、删除或迁移已有对象。遇到同 key 异 SHA/尺寸必须立即失败。
5. canonical `wiki_pages`、`wiki_media_links` 保持 importer 所有权；新增视觉资料只进入 supplement。
6. API 不返回 `local_relpath`、本地盘符、文件 URI、MinIO 密钥或源文件绝对路径。
7. 生产前端禁止 iframe、运行时 Stitch HTML、Tailwind CDN、远程 Google Fonts、整页 `transform: scale()` 和固定审稿画布。
8. Card Nav 保留；其他既有动效若妨碍批准构图，优先删除或降级。

## 4. 强制检查点

| 检查点 | 对应任务 | 硬性证据 |
|---|---|---|
| CP-01 | 真实数据与边界基线 | 3003 API/数据库/MinIO/manifest 清单、六张本地资源 SHA-1、RAG 关键文件哈希 |
| CP-02 | raw 结构化解析 | parser 单测先红后绿；槲寄生输出传承、5 级塑造、3 段文化、2 组 6 件藏品 |
| CP-03 | supplement schema 与安全媒体计划 | migration、序列化、dry-run、冲突拒绝测试通过；无写操作时结果可复现 |
| CP-04 | MySQL/MinIO 受控落地 | 只新增 6 个对象；supplement media 6 条；重跑 writes/uploads 均为 0；原对象数只增不减 |
| CP-05 | `/api/wiki` 合并契约 | 3003 返回显式 section/order/size/role；无本地路径；RAG API 测试不回归 |
| CP-06 | 纯前端详情 ViewModel | 真实 fixture 产出 2 皮肤、3 技能、3 传承、5 塑造、语音、3 文化、2 组 6 藏品 |
| CP-07 | 原生 PC/移动组件树 | 组件测试验证两套互斥模块树、Card Nav、Initial/Insight、固定栏与语音滚动语义 |
| CP-08 | Stitch 响应式样式 | PC 批准布局与移动九锚点的结构、材质、比例、字体和滚动所有权达到规格门槛 |
| CP-09 | 真实端到端与像素回归 | 8000+5173 真实数据；九张移动截图逐一对照；PC 截图对照；全部图片 naturalWidth > 0 |
| CP-10 | 全量回归与边界复核 | 前后端测试、构建、RAG smoke、只读网络审计、MinIO/MySQL 幂等证据全部通过 |

## 5. TDD 执行规则

每个检查点严格按以下顺序执行：

1. 先新增或修改最小失败测试。
2. 运行指定测试并记录预期失败原因；测试若意外通过，先查明测试是否有效。
3. 写最小实现使测试通过。
4. 运行该检查点全部测试。
5. 只在该检查点通过后进入下一项。

## 6. 任务明细

### CP-01：冻结真实数据与只读边界

**读取：**

- `data/raw/100-UTTU人物合辑/神秘学家｜Arcanists/槲寄生｜Druvis III.md`
- `data/huiji/res1999/resources_manifest.jsonl`
- `data/huiji/res1999/assets/files/**`
- `data/processed/huiji/dev/media_assets.jsonl`
- 当前项目 MySQL 的 `wiki_pages/wiki_page_supplements`
- 当前共享 MinIO 对象清单

**新增：**

- `eval/stitch-character-detail-20260715/baseline.json`

**验收：**

- page `char:3003`、route `/wiki/character/3003` 存在。
- raw 有 `传承`、`神秘术`、`塑造`、`单品`、`文化`、`语音`。
- `Belonging-300301..300306` 六条首选资源均存在于 manifest 和本地 files，实际 SHA-1 等于 manifest。
- 当前 MinIO 中这六个目标 supplement key 的存在状态被记录；不得根据数量推断命中。
- 保存 `data/processed/huiji/dev`、Milvus 配置和 RAG 关键模块哈希，CP-10 必须一致。

### CP-02：扩展 raw 角色结构化解析

**修改：**

- `src/huiji_wiki/raw_character_enrichment.py`
- `tests/fixtures/huiji_wiki/raw_character_sample.md`
- `tests/test_huiji_wiki_raw_character_enrichment.py`

**实现：**

- 保留 markdown-it 解析二级标题和表格。
- 为 Obsidian `tabs`、`ad-flex`、`[!culture]` 增加有界的逐行状态机；不得用整段贪婪正则抓取。
- 输出独立 section：`culture_dossier` 与 `collection`，避免继续依赖 canonical 中历史错位的 `culture/item` 命名。
- collection block 保存 group、groupEn、name、nameEn、value、description、ordinal；本地路径不进入 payload。
- culture block 保存标题、英文标题/标签与段落；保留真实顺序。
- schema version 升级，旧 supplement 可读取但 health 标记 stale。

**失败测试先验证：**

- 当前 parser 不输出 `culture_dossier/collection`。
- 槲寄生 fixture 的六件藏品与三段文化缺失。

**通过条件：**

- 解析输出顺序稳定、源输入不变、无绝对路径。
- 传承 3 行、塑造 LV.1-LV.5、文化 3 段、藏品 2 组 6 件。

### CP-03：资源映射、supplement media schema 与 dry-run

**新增：**

- `infra/mysql/migrations/20260715_wiki_character_visual_supplements.sql`
- `tests/test_huiji_wiki_character_visual_supplement.py`

**修改：**

- `scripts/enrich_wiki_from_raw.py`
- `src/huiji_wiki/raw_character_enrichment.py`
- `tests/test_huiji_wiki_supplement_migration.py`

**实现：**

- `wiki_page_supplements` 增加 nullable `media_links_json`，旧行保持兼容。
- 构建器从已匹配 page ID 提取 entity ID；按 `Belonging-{entityId}{ordinal:02d}` 在 manifest 中选择首选 WebP，缺失时选择 PNG。
- 校验 manifest SHA-1、实际文件 SHA-1、size、mime、width、height。
- 生成稳定 media ID、`sectionKey=collection`、`role=collection_item`、`displayOrder`、尺寸与 planned MinIO URL。
- dry-run 只生成 `eval/stitch-character-detail-20260715/media-plan.json`，不连接 MinIO 写入、不改数据库。

**安全要求：**

- 目标 key 为 `reverse1999/wiki-supplement/character/{entityId}/collection/{sha1}.{ext}`。
- 重复 manifest 名称、SHA 不符、本地文件缺失、对象冲突全部失败，不静默降级为远程灰机 URL。

### CP-04：幂等写入项目 MySQL 与共享 MinIO

**修改：**

- `scripts/enrich_wiki_from_raw.py`
- 必要时复用 `src/assets/minio_store.py`，只增加通用的严格 stat/冲突检查，不改变既有调用语义

**执行顺序：**

1. 对 supplement 相关行做 JSON 备份。
2. 应用 migration。
3. 运行 dry-run 并人工/脚本核对 6 个对象计划。
4. 显式 `--apply --upload-supplement-media` 执行加法上传和 supplement 事务写入。
5. 再运行相同命令验证幂等。

**通过条件：**

- 第一次仅新增缺失对象，不覆盖既有对象。
- 3003 supplement 中有 6 条 collection media link。
- 第二次 `uploaded=0`、`writes=0` 或等价 no-op。
- canonical 表行数和 RAG 产物哈希不变。

### CP-05：扩展只读 Wiki API 媒体契约

**修改：**

- `src/huiji_wiki/models.py`
- `src/huiji_wiki/repository.py`
- `backend/wiki.py`
- `tests/test_huiji_wiki_repository.py`
- `tests/test_huiji_wiki_api.py`

**实现：**

- repository 读取 `media_links_json`，与 canonical media 按 mediaId 去重后合并。
- safe media whitelist 增加 `sectionKey`、`displayOrder`、`sha1`、`width`、`height`、`variant` 等纯展示字段。
- 继续仅接受 HTTP(S) URL；拒绝 `local_relpath/objectKey/盘符/file://`。
- portrait supplement 可提供显式 `variant=initial|insight`；前端不从文件名猜。
- `/api/wiki/health` 继续独立；不改 `/health` 与 RAG response schema。

**通过条件：**

- `GET /api/wiki/pages/char%3A3003` 返回六条 `collection_item`。
- 返回顺序、尺寸、SHA 与 media ID 稳定。
- 所有 API/仓储回归通过。

### CP-06：建立纯角色详情 ViewModel

**新增：**

- `frontend/react-app/src/components/wiki/characterDetailViewModel.ts`
- `frontend/react-app/src/components/wiki/characterDetailViewModel.test.ts`

**修改：**

- `frontend/react-app/src/types/wiki.ts`
- `frontend/react-app/src/components/wiki/wikiViewModel.ts`
- 对应既有测试

**实现：**

- 由 `WikiPageViewModel` 生成专用 `CharacterDetailViewModel`。
- 明确字段：identity、summary cards、profile rows、portrait states、skills、inheritance levels、portray levels、voices、culture entries、collection groups、technical dossier。
- skills 按 heading/table/mediaIds 组合；ultimate 保持独立大卡。
- voices 按语言/事件分组，默认展示中文或可读首选语言，音频 URL 不铺入普通图片区。
- collection 只消费 `section=collection` structured blocks 与 `role=collection_item` media，不猜 URL/名称。
- `伤害类型` 展示值归一为英文 `Mental`，说明保留“精神创伤”；属性归一为 `Plant`。

**通过条件：**

- 使用真实 3003 fixture 精确断言所有数量、顺序、媒体关联和输入不可变。
- 缺失可选字段整块省略，不出现 `undefined`、空卡或伪造文案。

### CP-07：原生 PC 与移动详情组件树

**新增：**

- `frontend/react-app/src/components/wiki/character-detail/DesktopCharacterDossier.tsx`
- `frontend/react-app/src/components/wiki/character-detail/MobileCharacterDossier.tsx`
- `frontend/react-app/src/components/wiki/character-detail/CharacterPortraitStage.tsx`
- `frontend/react-app/src/components/wiki/character-detail/CharacterSkillCards.tsx`
- `frontend/react-app/src/components/wiki/character-detail/CharacterVoiceRecords.tsx`
- `frontend/react-app/src/components/wiki/character-detail/CharacterCulture.tsx`
- `frontend/react-app/src/components/wiki/character-detail/CharacterCollection.tsx`
- 对应组件测试

**修改：**

- `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.tsx`
- `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.test.tsx`
- `frontend/react-app/src/components/wiki/WikiShell.tsx`

**实现：**

- `WikiCharacterDetailPage` 接收专用 view model，不再接收八个任意 ReactNode 插槽。
- 使用 media query hook 在桌面与移动模块树间切换；不同时挂载两份可访问 DOM。
- Initial/Insight 同舞台互斥，`aria-hidden/aria-pressed/pointer-events` 与画面同步。
- 移动顺序严格对应九图；语音内层是唯一局部纵向滚动区。
- 移动底栏 `DOSSIER/ARCHIVE/COMBAT` 固定；ARCHIVE 返回选人状态，COMBAT 定位技能。
- PC 保持 6.8 节单视口档案工作台；左右档案列与中部舞台拥有正确滚动所有权。

### CP-08：像素级样式、字体与材质

**修改：**

- `frontend/react-app/src/components/wiki/WikiCharacterDetailPage.css`
- `frontend/react-app/src/styles/archival.css`
- `frontend/react-app/src/styles/themes.css`
- `frontend/react-app/index.html`
- `frontend/react-app/public/fonts/**`

**实现：**

- 本地化 Libre Caslon Text、JetBrains Mono 与中文正文所需字体；添加 `font-display: swap`，移除详情页对远程字体的依赖。
- 复刻深铜背景、细噪点、玻璃/纸张层、硬阴影、斜贴标签、轻微错位和边框密度。
- 不使用卡片套卡片；技能、文化、藏品各自使用 Stitch 对应模块构图。
- `375x850` 为移动主参考；`360x800/390x844/412x915` 连续适配，无横向滚动。
- PC 对照 6.8；`1280x951/1440x900/1920x1080` 连续适配，不整体缩放。
- reduced-motion 下关闭非必要位移和过渡，不改变布局。

### CP-09：真实 E2E 与九锚点视觉回归

**修改：**

- `frontend/react-app/e2e/wiki-archival.spec.ts`
- `frontend/react-app/playwright.config.ts`
- 必要时新增 `frontend/react-app/e2e/wiki-character-detail-visual.spec.ts`

**删除旧错误验收：**

- 不再要求移动语音和档案默认折叠。
- 不再以 `scrollHeight < 8000` 判定成功。
- 不再只验证“媒体区比资料区宽”或“区域存在”。

**新增硬门槛：**

- 新增 `375x850` 视觉项目。
- 九个锚点逐一截图，与 spec assets 对照；几何、字体角色、材质和固定栏使用严格阈值。
- 检查九段纵向覆盖连续，无模块断层。
- 六张藏品、两张立绘、三张技能图均 `naturalWidth > 0`。
- 页面无横向溢出；语音滚动到边界后全局页面仍可继续滚动。
- Back 恢复选人分类、搜索、选中角色与列表位置。
- 网络审计：Wiki 请求全 GET；MinIO 仅 GET；无 8001、file URL、盘符路径。

### CP-10：全量回归、真实烟测与证据归档

**后端：**

```powershell
python -m pytest tests/test_huiji_wiki_raw_character_enrichment.py tests/test_huiji_wiki_character_visual_supplement.py tests/test_huiji_wiki_supplement_migration.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_api.py -q
python -m pytest tests/test_huiji_wiki_*.py tests/test_sse.py tests/test_conversation_api.py -q
```

**前端：**

```powershell
npm test -- --run src/components/wiki src/api/wiki.test.ts
npm run build
npx playwright test e2e/wiki-archival.spec.ts e2e/wiki-character-detail-visual.spec.ts
```

**真实烟测：**

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/wiki/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/wiki/pages/char%3A3003"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ask" -ContentType "application/json" -Body '{"question":"介绍一下十四行诗","category":null}'
```

**最终证据：**

- `eval/stitch-character-detail-20260715/final-report.json`
- PC、移动九锚点实际截图
- screenshot hash/尺寸表
- MySQL supplement 计数与幂等报告
- MinIO 6 对象 URL/size/SHA 命中报告
- RAG 关键文件与 processed artifacts 哈希不变报告

## 7. 完成定义

只有同时满足以下条件才可完成：

1. CP-01 至 CP-10 全部通过，无“部分通过”。
2. 3003 真实 API 可完整驱动 PC 与移动详情，不使用测试假数组或原型硬编码。
3. 移动九张批准截图对应模块全部可达，六件藏品真实显示。
4. PC 与移动均达到 Stitch 构图，不是通用卡片列表近似。
5. Card Nav 保留且可用；Initial/Insight、ARCHIVE、COMBAT、Back 与语音滚动均通过交互验收。
6. 前端构建、前后端测试、E2E、RAG smoke 与只读边界审计全部通过。
7. MinIO/MySQL 重跑幂等；RAG/Milvus/processed artifacts 未被修改。

