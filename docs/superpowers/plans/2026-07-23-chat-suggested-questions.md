# 聊天推荐问题栏执行计划

## 1. 目标范围

本轮必须完成以下 specs P0 条目：

- 推荐内容：`SUGGEST-P0-01`、`SUGGEST-P0-02`、`SUGGEST-P0-03`
- 输入交互：`INPUT-P0-01`、`INPUT-P0-02`、`INPUT-P0-03`、`INPUT-P0-04`
- 展示与无障碍：`UI-P0-01`、`UI-P0-02`、`UI-P0-03`、`A11Y-P0-01`

本轮只修改 `frontend/react-app`。不增加后端接口、持久化字段、依赖包或聊天 store 字段。

本轮不执行任何 P1/P2：不实现“换一批”、草稿撤销、分类/上下文推荐、模型生成、分析事件、滚动控制按钮和推荐动效。

## 2. 强制验收门槛

| Specs 编号 | 实现位置 | 自动测试/命令 | 真实验收 | 失败时表现 |
| --- | --- | --- | --- | --- |
| `SUGGEST-P0-01` | `SuggestedQuestions.tsx` 本地题库 | `SuggestedQuestions.test.tsx` 检查题库为 10–12 条并覆盖约定主题 | 打开聊天页，4 条推荐均为可直接提问的完整中文问题 | 数量越界、内容不是完整问题或主题过于单一 |
| `SUGGEST-P0-02` | `sampleSuggestedQuestions` | 纯函数测试：4 条上限、唯一性、原数组不变、小题库 | 重载页面多次，推荐组允许变化且单组无重复 | 同组重复、超过 4 条、小题库报错或原题库被改写 |
| `SUGGEST-P0-03` | `SuggestedQuestions` 挂载期状态 | 重渲染后按钮文本数组保持一致 | 编辑草稿、发送/完成、切换分类、清空对话时当前 4 条不跳变 | 用户阅读期间推荐项自行变化 |
| `INPUT-P0-01` | `ChatInput.tsx` 选择回调与 input ref | Testing Library 点击后断言新值与焦点 | 先输入草稿再点推荐项，草稿被完整替换且光标回到输入框 | 只追加文本、未聚焦或草稿未更新 |
| `INPUT-P0-02` | `SuggestedQuestions.tsx` 的 `type="button"`；`ChatInput.tsx` 的选择回调 | `ChatInput.test.tsx` 点击后断言 `send` 未调用 | 点击推荐项后消息区不新增消息，发送按钮变为可用 | 点击即发起网络请求或新增消息 |
| `INPUT-P0-03` | `ChatInput.tsx` 常驻渲染与 `sending` 透传 | `ChatInput.test.tsx`、`ChatSection.test.tsx`：空/非空消息状态均存在推荐组；发送中按钮全部 disabled | 发起一次真实提问，流式响应期间不可点，结束后恢复且内容不变 | 推荐栏随消息消失、发送中仍可点或结束后未恢复 |
| `INPUT-P0-04` | `ChatInput.tsx`、`ChatSection.tsx`、既有 `chatStore.ts` 接口边界 | 相关组件测试、完整 `npm test`、`npm run build` | 手动发送问题并切换扩大检索/自由补充，旧流程行为不变 | 发送、重试、模式按钮、清空或分类筛选回归 |
| `UI-P0-01` | `SuggestedQuestions.css` 与表单内渲染顺序 | 组件结构断言；构建通过 | 2048×1157 下推荐栏位于截图红框区域且不遮挡其他控件 | 推荐栏进入消息区、遮挡输入/发送/模式按钮 |
| `UI-P0-02` | `SuggestedQuestions.css` 的 flex、`white-space` 与 `overflow-x` | `SuggestedQuestions.css.test.ts` 静态断言；390×844 真实浏览器检查 | 390×844 下推荐列表横向滚动，页面仍可操作且不持续增高 | 按钮多行挤压消息区或溢出页面 |
| `UI-P0-03` | `SuggestedQuestions.css` 的主题变量与 `color-mix` | `SuggestedQuestions.css.test.ts` 禁止独立主题色块；`npm run build` | `manuscript-gold`、`storm-dark` 下文字、边框和状态均清晰 | 某一主题低对比、出现固定浅/深色块 |
| `A11Y-P0-01` | `SuggestedQuestions.tsx` 的分组/按钮语义；`SuggestedQuestions.css` 的交互状态 | `SuggestedQuestions.test.tsx` role/name/disabled/键盘测试；`SuggestedQuestions.css.test.ts` 焦点规则断言 | Tab 可逐项聚焦，Enter/Space 只填草稿，焦点轮廓可见 | 无可访问名称、键盘不可用、按键提交或无焦点提示 |

完成判定：表中所有 P0 均有自动测试结果和对应真实验收记录；完整测试与构建通过；任何一项只有占位或只通过 mock 都不得标记完成。

## 3. 执行步骤

### Step 1：建立推荐题库与无重复抽样

- 对应 specs：`SUGGEST-P0-01`、`SUGGEST-P0-02`
- 新建：`frontend/react-app/src/components/chat/SuggestedQuestions.tsx`
- 新建测试：`frontend/react-app/src/components/chat/SuggestedQuestions.test.tsx`
- 实现要点：
  - 定义 12 条完整中文问题，覆盖人物、心相、剧情、世界、阵营、日历。
  - 导出 `sampleSuggestedQuestions(pool, count = 4, random = Math.random)`。
  - 复制候选数组后按随机索引逐项移除，保证不修改原数组且不重复。
  - 空题库返回空数组；不足 4 条返回全部可用项。
- TDD 测试：
  1. 先写题库规模/主题、唯一性、数量上限、原数组不变和小题库测试。
  2. 运行 `npm test -- --run src/components/chat/SuggestedQuestions.test.tsx`，确认因模块不存在而 RED。
  3. 写最小实现，再运行同一命令确认 GREEN。
- 验收：使用注入的固定随机函数得到确定结果；手动刷新页面多次时推荐组可变化但单组不重复。
- 失败处理：若测试因导入或语法错误失败，先修复测试到“缺少行为”的预期失败，再进入实现；不得用删减断言换取通过。

### Step 2：实现挂载期稳定的推荐组件

- 对应 specs：`SUGGEST-P0-03`、`INPUT-P0-03`、`A11Y-P0-01`
- 修改：`frontend/react-app/src/components/chat/SuggestedQuestions.tsx`
- 修改测试：`frontend/react-app/src/components/chat/SuggestedQuestions.test.tsx`
- 实现要点：
  - 组件首次挂载时抽样一次，并把结果保存在挂载期状态中。
  - 接口为 `disabled: boolean`、`onSelect(question: string)`；允许显式传入 questions 以便确定性组件测试。
  - 根节点使用 `role="group" aria-label="推荐问题"`。
  - 每条问题使用带唯一 key 的原生 `button type="button"`，透传 disabled 并调用选择回调。
- TDD 测试：
  1. 先写可访问分组、4 个按钮、选择回调、disabled 和重渲染稳定性测试。
  2. 运行聚焦测试并确认缺少组件行为导致 RED。
  3. 写最小组件，重跑确认 GREEN。
- 真实验收：加载页面后编辑输入、切换分类和清空对话，记录推荐文字并确认不变化。
- 失败处理：若 `onSelect` 触发表单提交或重渲染重新抽样，本步骤不得完成。

### Step 3：接入聊天草稿而不触发发送

- 对应 specs：`INPUT-P0-01`、`INPUT-P0-02`、`INPUT-P0-03`、`INPUT-P0-04`
- 修改：`frontend/react-app/src/components/chat/ChatInput.tsx`
- 新建测试：`frontend/react-app/src/components/chat/ChatInput.test.tsx`
- 修改测试：`frontend/react-app/src/components/sections/ChatSection.test.tsx`
- 实现要点：
  - 为现有文本输入增加 `useRef<HTMLInputElement>`。
  - 选择回调只执行 `setValue(question)` 与 `inputRef.current?.focus()`。
  - 推荐组件作为 form 的第一个子节点，位于输入行之前；`disabled` 使用现有 `sending`。
  - 不修改 `chatStore.send`、route options、重试和清空逻辑。
- TDD 测试：
  1. 先写“覆盖现有草稿并聚焦”“不调用 send”“发送中禁用”“空/非空消息均显示”的测试。
  2. 运行 `npm test -- --run src/components/chat/ChatInput.test.tsx src/components/sections/ChatSection.test.tsx`，确认推荐组缺失导致 RED。
  3. 完成最小接入，重跑并确认 GREEN。
- 真实验收：选择推荐后消息区不新增消息；点击发送后才进入既有流式问答；扩大检索、自由补充、分类和清空仍可用。
- 失败处理：若真实发送链路不可用，记录环境错误，但必须先确认点击推荐本身未发请求；既有流程回归则修复后重跑完整前端测试。

### Step 4：完成主题化样式与响应式布局

- 对应 specs：`UI-P0-01`、`UI-P0-02`、`UI-P0-03`、`A11Y-P0-01`
- 新建：`frontend/react-app/src/components/chat/SuggestedQuestions.css`
- 修改：`frontend/react-app/src/components/chat/SuggestedQuestions.tsx`（导入 CSS）
- 修改测试：`frontend/react-app/src/components/chat/SuggestedQuestions.test.tsx`
- 新建测试：`frontend/react-app/src/components/chat/SuggestedQuestions.css.test.ts`
- 实现要点：
  - 推荐栏采用 flex，左侧固定“试着问问”，右侧推荐列表 `min-width: 0`、`overflow-x: auto`。
  - 推荐项为不换行胶囊按钮，定义 hover、`focus-visible` 和 disabled。
  - 仅使用 `--bg-elevated`、`--text-*`、`--accent-gold`、`--border-*` 等现有变量和 `color-mix`。
  - 窄屏允许标签与列表上下排列，但问题按钮保持单行横向滚动。
- 测试：
  - `SuggestedQuestions.css.test.ts` 必须读取 CSS 并断言推荐列表包含 `overflow-x: auto`、推荐按钮包含 `white-space: nowrap`、存在 `:focus-visible` 与 `:disabled` 规则，且颜色声明引用现有 `var(--*)` 或 `color-mix`。
  - 运行 `npm test -- --run src/components/chat/SuggestedQuestions.test.tsx src/components/chat/SuggestedQuestions.css.test.ts src/components/chat/ChatInput.test.tsx src/components/sections/ChatSection.test.tsx`。
- 真实验收：
  - 2048×1157、`manuscript-gold`：位置对应截图红框，4 条按钮可见或在栏内滚动，不遮挡输入区。
  - 390×844、`manuscript-gold`：列表横向滚动，输入/发送/模式按钮仍完整可用。
  - 2048×1157 与 390×844、`storm-dark`：文字、边框、hover、焦点和 disabled 状态可辨认。
  - 键盘 Tab、Enter、Space 完成一次选择，确认只填充草稿。
- 失败处理：出现纵向多行挤压、页面横向溢出、主题低对比或焦点不可见时，不进入最终验证。

### Step 5：完整回归与 P0 闭环

- 对应 specs：全部 P0。
- 检查范围：所有本轮新建/修改的 React 前端文件。
- 自动验证：

```powershell
cd D:\1999Wiki\frontend\react-app
npm test
npm run build
```

- 真实数据/集成验证：启动当前本地前后端，完成以下链路并记录结果：
  1. 打开聊天页，记录首次随机 4 条推荐。
  2. 选择推荐，编辑草稿，确认选择阶段没有新增消息或网络问答请求。
  3. 提交问题，确认真实流式回答开始；发送中推荐禁用，结束后恢复且文本未变化。
  4. 切换检索范围和两种检索模式，清空对话，确认推荐栏常驻且当前推荐组不变。
  5. 在强制验收门槛规定的两种视口和两个主题完成视觉/键盘检查。
- 失败处理：完整测试、构建或任一真实链路失败时，定位到对应 specs 编号，补充失败测试后修复；不得以其余测试通过替代该项验收。

## 4. 可选任务

本轮无可选任务。只有全部 P0 通过且用户另行授权后，才可开启：

- `SUGGEST-P1-01`：用户主动“换一批”。
- `INPUT-P1-01`：覆盖草稿后的撤销能力。
- `UI-P1-01`：横向溢出的渐隐提示或滚动按钮。

以上 P1 不得在本轮顺手实现。

## 5. Deferred / Out of Scope

- `SUGGEST-P2-01`：按检索范围、上下文或热度动态推荐。
- `SUGGEST-P2-02`：后端或模型动态生成。
- `INPUT-P2-01`：推荐曝光、选择和发送分析。
- `UI-P2-01`：推荐切换和排序动效。
- 后端 API、数据库、Zustand store 字段和新依赖包均不在本轮范围。

## 6. 完成后自检表

- [ ] `SUGGEST-P0-01`：题库为 10–12 条并覆盖约定主题。
- [ ] `SUGGEST-P0-02`：最多 4 条、无重复、不修改原数组，小题库安全。
- [ ] `SUGGEST-P0-03`：同一挂载期不因草稿、发送、分类或清空而重抽样。
- [ ] `INPUT-P0-01`：选择后覆盖草稿并聚焦输入框。
- [ ] `INPUT-P0-02`：选择阶段不调用 send、不新增消息。
- [ ] `INPUT-P0-03`：空/非空对话均常驻，发送中禁用且结束后恢复。
- [ ] `INPUT-P0-04`：发送、重试、检索模式、分类和清空无回归。
- [ ] `UI-P0-01`：位置正确且不遮挡现有控件。
- [ ] `UI-P0-02`：窄屏横向滚动且不持续挤压消息区。
- [ ] `UI-P0-03`：明暗主题均清晰，未引入单主题硬编码色块。
- [ ] `A11Y-P0-01`：分组命名、按钮语义、键盘与焦点状态可用。
- [ ] 相关 Vitest 已先观察 RED，再完成 GREEN。
- [ ] 完整 `npm test` 通过。
- [ ] `npm run build` 通过。
- [ ] 真实问答链路、双视口、双主题和键盘验收已记录。
- [ ] P1 均未执行或已明确另行授权；P2 未进入实现。
