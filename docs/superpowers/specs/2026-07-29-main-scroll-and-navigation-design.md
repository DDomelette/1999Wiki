# 主页面滚动与导航修复设计

日期：2026-07-29
状态：待用户审阅
范围：首页、资料分类页、问答页、主站与 Wiki 之间的导航

## 1. 背景与问题

当前主页面包含两个纵向页面导航滚动容器：

1. `.snap-container` 管理首页、资料外壳、问答页；
2. `.data-section__scroll` 管理资料外壳内部的多个全屏分类。

桌面滚轮导航通过 JavaScript 将两层滚动目标拼成一条逻辑序列，但移动端触摸滚动仍由浏览器分别处理两个物理滚动容器。小屏样式又将 `scroll-snap-type` 从 `mandatory` 降为 `proximity`，并将 `scroll-snap-stop` 从 `always` 降为 `normal`，导致快速滑动可以跨过只有一屏高度的资料外壳。

视口缩放、移动浏览器地址栏变化和软键盘出现时，两层容器会分别保留旧的像素滚动位置，因此可能短暂显示相邻页面，直到下一次滚动重新触发吸附。

导航还存在两套不一致的实现：

- 主页面导航使用 `[data-snap-section]` 加 `scrollIntoView`；
- Wiki 导航中的“问答”使用 `/#chat`，但主页面没有可解析的 `#chat` 目标或挂载后恢复逻辑。

因此，从 Wiki 点击“问答”会加载主页面，但停留在默认首页。

## 2. 已批准的体验目标

采用单一主滚动序列：

```text
首页
→ 人物资料
→ 心相资料
→ 剧情资料
→ 其他资料分类
→ 问答页
```

每个项目均为独立全屏吸附页面。资料分类不再拥有独立的纵向页面导航滚动容器。

问答页仍然固定为一屏高，并保留消息列表内部滚动：

```text
问答页
├─ 工具栏
├─ 消息列表（独立滚动）
└─ 输入区
```

用户已批准以下聊天边界行为：

- 消息列表尚可滚动时，由消息列表优先消费输入；
- 消息列表位于顶部，用户继续做“返回上一页”的滚动手势时，允许回到最后一个资料分类；
- 消息列表位于底部，继续向后滚动不离开问答页，因为问答页是主序列终点；
- 边界切页必须经过方向和距离阈值，避免阅读聊天记录时误触发。

## 3. 方案比较

### 3.1 方案 A：统一为一个主纵向滚动容器（批准并推荐）

首页、每个资料分类和问答页都成为 `.snap-container` 的吸附目标。`DataSection` 只负责资料分组和浮动/粘性分类导航，不再负责纵向滚动。

优点：

- DOM 高度和用户看到的页面序列一致；
- 移动端惯性滚动不会绕过整个资料区；
- 缩放时只需恢复一个主滚动位置；
- 导航、滚动侦测和自定义滚动条共享同一坐标系；
- 桌面滚轮、移动触摸和导航点击使用同一目标序列。

代价：

- 需要调整 `DataSection` 的布局边界；
- 资料导航必须改成在整个资料区间内保持 sticky/overlay，而不是依赖内层滚动容器；
- 现有桌面滚轮导航和测试需要按新的单层结构重写。

### 3.2 方案 B：保留双层滚动并增加移动端手势锁

保留现有结构，用触摸事件判断资料内层是否到达边界，再决定是否把手势交给外层。

优点是代码改动表面上较小；缺点是需要维护两层位置、滚动链、缩放恢复和 iOS/Android 手势差异。导航的 `scrollIntoView` 仍可能同时滚动两个祖先容器。

该方案只能缓解症状，不采用。

### 3.3 方案 C：仅移动端展平，桌面保留双层

移动端使用单层滚动，桌面继续使用资料内层滚动。

它能降低移动端风险，但会形成两套 DOM/CSS/滚动侦测和导航逻辑，测试矩阵显著扩大。当前视觉和交互并不要求桌面必须保留物理内层滚动，因此不采用。

## 4. 目标架构

### 4.1 单一页面滚动所有者

`.snap-container` 是页面级纵向滚动的唯一所有者，包含以下语义目标：

- `home`
- `data:{categoryKey}`，按接口返回顺序排列
- `chat`

`DataSection` 不再作为额外的一屏吸附目标。它作为资料分类的结构分组存在，其内容高度由分类面板自然撑开。每个 `CategoryPanel` 保持 `100dvh` 全屏高度和主容器吸附属性。

资料加载期间必须渲染一个稳定的 `data:loading` 占位屏，避免异步分类尚未返回时，页面序列暂时变成“首页 → 问答”。分类返回后，占位屏替换为真实分类；若用户当时位于资料占位屏，恢复到第一个真实分类。

### 4.2 资料分类导航

资料分类导航在资料分组范围内使用 sticky/overlay 定位：

- 进入第一个资料分类时出现；
- 在所有资料分类之间保持可见；
- 离开最后一个分类进入问答页时退出；
- 点击分类时只操作主滚动容器，不调用全局 `scrollIntoView`。

移动端继续使用横向标签栏，桌面继续使用纵向分类栏。此次不改变资料页视觉设计，只改变滚动所有权和定位方式。

### 4.3 问答页内部滚动

问答页保持 `100dvh`，布局继续使用：

- 工具栏：固定尺寸；
- 消息区域外壳：`flex: 1; min-height: 0`；
- 消息列表：`overflow-y: auto`；
- 输入区：固定在问答页底部，并适配安全区和软键盘。

消息滚动和页面滚动通过统一的边界仲裁规则处理。

桌面滚轮：

- 消息列表在滚动方向上仍有剩余空间时，不触发页面切换；
- 位于顶部并继续向上一页面滚动时，切换到最后一个资料分类；
- 位于底部并继续向下一页面滚动时保持在问答页。

移动触摸：

- 手势起始时记录消息列表位置和方向；
- 普通聊天滚动不阻止浏览器原生行为；
- 仅当消息列表已在顶部，并且手势明确指向上一页面、累计距离超过阈值后，才触发一次主页面切换；
- 一次手势最多切换一个页面，并在吸附完成前锁定重复切换；
- 阈值使用独立常量并由交互测试约束，不与视口像素高度硬编码绑定。

语义上，“返回上一页”指内容向下移动、用户手指向下拖动；实现测试同时使用滚动增量方向，避免中文动作描述造成方向歧义。

### 4.4 缩放、地址栏和软键盘

系统保存当前语义目标 ID，而不是保存“第几屏 × 旧视口高度”的推导结果。

以下事件发生后重新对齐当前语义目标：

- `window.resize`
- `visualViewport.resize`
- 横竖屏切换
- 浏览器缩放导致的布局视口变化

重新对齐规则：

1. 等待本轮布局稳定并合并连续 resize 事件；
2. 使用 `behavior: auto` 对齐当前目标，避免缩放时叠加平滑动画；
3. 若当前目标已经卸载，则使用最近的合法目标；
4. 问答输入框聚焦导致软键盘出现时，保持 `chat` 为主目标，只压缩消息区域；
5. 不改变用户在聊天消息列表中的 `scrollTop`，除非消息内容自身发生追加。

主容器在所有受支持视口上恢复 `scroll-snap-type: y mandatory` 和 `scroll-snap-stop: always`。是否启用平滑动画由导航动作决定，不在容器上全局声明 `scroll-behavior: smooth`，避免 resize、历史恢复和内容加载也被强制动画化。

## 5. 统一导航设计

新增唯一的主页面语义导航入口 `navigateToMainSection(target, options)`。调用方不再直接查询 DOM 或调用 `scrollIntoView`。

它负责：

- 校验目标是否存在；
- 等待异步资料分类挂载；
- 计算目标相对主滚动容器的偏移；
- 调用主容器 `scrollTo`；
- 更新 URL；
- 在导航完成后更新当前语义目标。

### 5.1 URL 约定

稳定公开目标使用：

- `/#home`
- `/#data`
- `/#chat`

资料分类使用 `/#data/<encodedCategoryKey>`，其中分类键严格通过 `encodeURIComponent(categoryKey)` 编码，并由集中转换函数生成和解析，不允许导航组件自行拼接。

`#data` 在分类已加载时解析为第一个资料分类；加载失败时解析到资料错误/占位屏。

### 5.2 同页导航

主页面导航点击“首页”“资料”“问答”时：

1. 关闭导航菜单；
2. 调用统一语义导航入口；
3. 明确滚动 `.snap-container`；
4. 使用平滑动画；
5. 将 hash 更新为对应目标。

### 5.3 跨页导航

Wiki 中的“问答”链接继续生成可复制、可前进后退的 `/#chat` URL。主应用挂载后读取 hash，等待目标可用，再使用统一入口对齐。

这会修复当前 `/#chat` 仅加载主页面、却停在首页的问题。

### 5.4 历史导航

监听 `hashchange` 和浏览器前进/后退事件：

- URL 变化时恢复对应语义目标；
- 滚动侦测更新当前状态，但不会在每个滚动像素写入历史；
- 用户主动完成一次页面吸附后，使用 `replaceState` 同步当前 hash；
- 导航栏明确点击使用 `pushState` 创建一条可返回记录；
- resize、软键盘和异步分类挂载造成的重新对齐不写入历史。

## 6. 状态与滚动侦测

`useScrollSpy` 的观察根节点显式设置为 `.snap-container`，只观察实际吸附目标：

- `home`
- `data:{key}`
- `chat`

不再同时观察资料父壳和资料子分类，避免父子目标竞争更新 Zustand 状态。

状态继续保留：

- `currentSection`
- `currentCategory`

可增加内部派生的 `currentSnapTarget`，但 URL、导航和滚动代码使用同一个转换函数，禁止各自拼接目标字符串。

## 7. 需要放弃或调整的现有机制

### 明确放弃

1. 资料页独立纵向滚动容器；
2. 移动端页面级 `scroll-snap-type: proximity`；
3. 移动端页面级 `scroll-snap-stop: normal`；
4. 使用全局 `document.querySelector(...).scrollIntoView()` 作为主导航机制；
5. 在主滚动容器上全局开启 `scroll-behavior: smooth`；
6. 将资料父壳和资料分类同时注册为页面吸附目标。

### 保留

1. 首页、资料分类、问答页的全屏叙事；
2. 桌面一次滚轮只切换一个页面的节制感；
3. 移动端原生触摸滚动；
4. 资料分类导航的桌面纵向、移动横向视觉；
5. 问答消息列表独立滚动；
6. 问答工具栏、输入区和安全区布局；
7. 自动隐藏的全局滚动条和聊天局部滚动条。

### 行为变化

全局滚动条将真实反映“首页 + 所有资料分类 + 问答”的完整长度，不再只显示三个外层页面的长度。这是预期修正。

## 8. 预期效果

### 移动端

- 从首页快速滑动最多跨越一个吸附目标，不再直接跳过整个资料区；
- 资料分类按顺序进入，页面高度与滚动条进度一致；
- 缩放、地址栏变化和横竖屏切换后仍保持当前语义页面；
- 问答消息可独立阅读，只有在顶部继续明确拖动时才返回资料页；
- 软键盘仅压缩消息列表，不暴露相邻页面。

### 桌面端

- 保留滚轮逐屏切换体验；
- 资料分类仍按原顺序逐屏展示；
- 导航栏分类跳转更稳定；
- 不再依赖一次 `scrollIntoView` 同时协调两个滚动容器。

### 导航

- 主页面“问答”稳定到达问答页；
- Wiki“问答”从跨路由入口稳定到达问答页；
- 复制 `/#chat`、刷新、前进和后退均能恢复问答页；
- 分类数据延迟加载不会使导航错误地回到首页。

## 9. 风险与控制

### Sticky 资料导航的包含块

资料分组的高度和 overflow 设置会影响 sticky。实现时必须确保资料分组祖先不创建额外纵向滚动容器，也不使用会破坏 sticky 的裁剪方式。装饰层如需裁剪，应放在面板内部。

### 动态分类数量

分类接口可能返回空集合、延迟或错误。占位屏必须参与主序列，并在真实分类替换时保持当前语义位置。

### iOS 触摸与回弹

不依赖单纯的 scroll chaining 实现聊天顶部返回。触摸边界仲裁只在顶部、正确方向和超过阈值时介入，并验证 iOS WebKit。

### 动画与无障碍

`prefers-reduced-motion` 下，导航和 resize 对齐均使用即时滚动。焦点不能因为页面切换丢失；导航菜单关闭后不强制把焦点移入不可见页面。

## 10. Kimi CLI 实施与 Codex 监督

### 10.1 执行责任

本修复的运行代码和测试修改由 Kimi CLI 执行，Codex 不直接编写实现代码。职责固定如下：

- Kimi CLI：按照已批准规格和后续实施计划编写失败测试、实现代码及必要的测试调整；
- Codex：拆分批次、生成任务提示、限定文件范围、监督进程、审查 diff、独立运行验证、决定接受或退回；
- 用户：审阅规格、实施计划和最终结果，决定是否将工作树分支集成回主分支。

Kimi CLI 不得自行改变已批准架构、扩大任务范围或跳过失败测试。需要改变规格时必须停止当前批次，由 Codex 向用户报告并重新取得批准。

### 10.2 独立工作树

实施固定在以下已创建的独立工作树中进行：

- 工作树：`D:\1999Wiki\.worktrees\main-scroll-navigation-fix`
- 分支：`codex/main-scroll-navigation-fix`
- 起点：提交 `48b1bd2`

Kimi CLI 的每次调用都必须以该工作树或其 `frontend/react-app` 子目录为当前目录。禁止在 `D:\1999Wiki` 主工作区编写、格式化或暂存实现文件。

主工作区已有的无关修改不复制、不暂存、不清理。工作树分支未经用户批准不合并、不变基、不推送。

工作树创建后的前端基线为：

- 51 个 Vitest 测试文件通过；
- 278 项 Vitest 测试通过；
- 0 项失败。

后续失败必须能够归因于本修复批次，不得将失败解释为既有基线问题。

### 10.3 Kimi CLI 调用约束

使用已验证的 Kimi CLI：

- 可执行文件：`D:\KIMI\Kimi_Cli\bin\kimi.exe`
- 已验证版本：`0.26.0`
- 调用模式：非交互 `--prompt`；Kimi CLI 0.26.0 的 prompt 模式禁止组合 `--auto` 或 `--yolo`

每次提示必须包含：

1. 当前批次唯一目标；
2. 本规格绝对路径；
3. 允许修改的精确文件白名单；
4. 必须先运行并展示的失败测试；
5. 完成后必须运行的聚焦测试；
6. 禁止 Git 提交、安装依赖、修改配置或处理白名单外文件；
7. 输出修改摘要、测试结果和已知风险。

Kimi CLI 不得执行 `git commit`、`git push`、`git merge`、`git rebase`、`git reset`、`git clean` 或删除工作树。不得启动新的代理、工作树或后台实现进程。

Kimi CLI 额度耗尽、鉴权失败、非零退出、中途停止、没有有效 diff 或连续两次无法通过同一批次验证时，Codex 停止实施并向用户报告。Codex 不在未获额外授权时接管编写实现代码。

### 10.4 文件白名单

Kimi CLI 只允许修改或创建以下文件：

```text
frontend/react-app/src/App.tsx
frontend/react-app/src/App.wheel.test.tsx
frontend/react-app/src/styles/global.css
frontend/react-app/src/hooks/useScrollSpy.ts
frontend/react-app/src/hooks/useScrollSpy.test.tsx
frontend/react-app/src/hooks/useWheelSnapNavigation.ts
frontend/react-app/src/hooks/useWheelSnapNavigation.test.tsx
frontend/react-app/src/hooks/useMainViewportAlignment.ts
frontend/react-app/src/hooks/useMainViewportAlignment.test.tsx
frontend/react-app/src/hooks/useChatPageBoundaryNavigation.ts
frontend/react-app/src/hooks/useChatPageBoundaryNavigation.test.tsx
frontend/react-app/src/navigation/mainSectionNavigation.ts
frontend/react-app/src/navigation/mainSectionNavigation.test.ts
frontend/react-app/src/components/navigation/navigationConfig.ts
frontend/react-app/src/components/navigation/RouteAwareCardNav.tsx
frontend/react-app/src/components/navigation/RouteAwareCardNav.test.tsx
frontend/react-app/src/components/sections/DataSection.tsx
frontend/react-app/src/components/sections/DataSection.css
frontend/react-app/src/components/sections/ChatSection.tsx
frontend/react-app/src/components/sections/ChatSection.css
frontend/react-app/src/components/sections/ChatSection.test.tsx
frontend/react-app/src/components/sections/MainResponsiveCss.test.ts
frontend/react-app/e2e/main-mobile-responsive.spec.ts
```

白名单外文件出现任何修改即判定该批次越界。Codex 必须先停止 Kimi CLI，审查越界原因；未经用户批准，不接受通过扩大白名单来迁就实现。

禁止修改：

- API、聊天 Store、主题 Store 和 Wiki 数据模型；
- `/wiki/*` 页面组件与 Wiki 阅读布局；
- 后端、依赖版本、锁文件和构建配置；
- 当前规格和后续实施计划；
- 主工作区的任何文件。

### 10.5 分批监督门禁

实施拆为四个串行批次：

1. 语义目标、URL/hash 转换和同页/跨页导航；
2. 资料区展平、单一主滚动序列、滚轮与 ScrollSpy；
3. 问答消息边界、触摸返回和视口变化恢复；
4. 移动端 WebKit/Chromium 端到端回归与最终收口。

每个批次遵循同一监督循环：

1. Codex 记录批次开始前 `git status`；
2. Codex 调用 Kimi CLI 执行一个批次；
3. Codex 检查进程退出状态和 Kimi 摘要；
4. Codex 比较批次前后文件列表，拒绝白名单外修改；
5. Codex 运行 `git diff --check` 并逐文件审查实现是否符合规格；
6. Codex 独立运行聚焦测试；
7. 聚焦测试通过后运行受影响的组合测试；
8. 批次通过监督门禁后，仅由 Codex 创建该批次提交；
9. 批次失败则把具体证据反馈给 Kimi CLI，最多允许一次针对性修正。

Codex 不以 Kimi CLI 自报“完成”作为验收依据。只有工作树中的 diff、测试输出和浏览器行为共同通过，批次才算完成。

最终验收必须运行完整 Vitest、生产构建及本规格要求的 Playwright 项目。最终结果留在 `codex/main-scroll-navigation-fix` 分支，等待用户审阅和决定集成方式。

## 11. 测试与验收

### 单元测试

1. 主序列目标顺序为首页、全部资料分类、问答；
2. 不再存在资料纵向滚动所有者；
3. 语义目标与 URL hash 双向转换；
4. `/#chat` 在资料异步加载前后均解析为问答；
5. 消息列表未到边界时消费滚轮；
6. 消息列表顶部的上一页意图只切换一次；
7. 消息列表底部不会越过问答页；
8. resize 恢复当前语义目标且使用即时滚动。

### 浏览器端到端测试

至少覆盖 Chromium 移动模拟和 WebKit 移动模拟：

1. 从首页执行一次高速触摸滑动，不能直接到问答；
2. 连续滑动依次经过每个资料分类；
3. 在问答页滚动长消息，不改变主容器位置；
4. 聊天顶部明确向上一页面拖动，回到最后一个资料分类；
5. 问答页从 390×844 缩到 390×568，不露出资料页；
6. 资料页缩放后保持同一分类；
7. 软键盘出现时输入框可见，主目标仍为问答；
8. 主页面导航“问答”到达问答；
9. 从 Wiki 点击“问答”到达问答；
10. 直接打开和刷新 `/#chat` 到达问答；
11. 浏览器前进/后退恢复正确页面；
12. 全局滚动条长度与实际吸附目标数量一致。

### 不回归项

- 320、360、390、412、768 像素宽度的现有视觉验收；
- 桌面资料海报布局；
- 分类导航点击区域；
- 聊天长消息、代码块、表格和媒体内部滚动；
- 减少动态效果模式；
- Wiki 独立文档页面的常规滚动。

## 12. 完成标准

以下条件全部满足才视为修复完成：

1. 页面级只有一个纵向滚动所有者；
2. 首页不能通过一次移动端快速滑动跨过整个资料区；
3. 三类缩放场景后当前语义页面保持不变；
4. 问答消息内部滚动和顶部返回资料均符合批准行为；
5. 主站与 Wiki 的“问答”导航、直接 URL 和历史导航一致；
6. 新增回归测试通过，现有主页面、聊天和 Wiki 测试无回归；
7. 所有实现修改均由 Kimi CLI 在指定工作树和白名单内产生；
8. Codex 已完成逐批 diff 审查、独立验证和最终验收；
9. 主工作区无本任务实现改动，工作树分支未经用户批准未被集成。
