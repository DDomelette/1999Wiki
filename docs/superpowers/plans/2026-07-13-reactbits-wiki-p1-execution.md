# React Bits 与 Wiki P1 执行计划

**状态：** 已获用户批准，2026-07-13 开始执行。

**前置门槛：** P0 的 104 项要求已全部通过，证据位于 `eval/wiki-reactbits-p0/`。P1 不得改写 RAG 产物、active pointer、Milvus collection；MinIO 缩略图只能由显式运维命令写入独立前缀，测试和页面请求保持只读。

## 检查点

### P1-01 动效预览与性能降级

- 覆盖：`MOTION-P1-01..02`、`QUALITY-P1-01`。
- 实现：开发态动效预览路由；统一能力/性能策略；记录初始化耗时、WebGL fallback 原因和图片失败数。
- 验收：策略单测；reduced-motion 与低性能模拟；诊断数据不进入公开 API。

### P1-02 导航上下文

- 覆盖：`NAV-P1-01..02`。
- 实现：Card Nav 根据 Wiki 页面类型调整强调色和分组排序；本地记录最近访问页面并提供快捷入口。
- 验收：路由、排序、持久化上限和失效链接测试。

### P1-03 语音体验

- 覆盖：`VOICE-UI-P1-01..02`。
- 实现：播放行进度状态；会话级角色语言偏好，不改变后端 cursor/language 契约。
- 验收：播放进度、切换、分页和语言回退测试。

### P1-04 图片画廊

- 覆盖：`IMAGE-UI-P1-01..02`。
- 实现：当前图片同源大图查看层；纹理窗口与预加载预算，保留 DOM fallback。
- 验收：键盘关闭、焦点恢复、窗口边界、单图失败与 WebGL fallback 测试。

### P1-05 Wiki 布局配置

- 覆盖：`WIKI-LAYOUT-P1-01..02`。
- 实现：页面类型动效 profile；移动端 PageIndex 顶部抽屉。
- 验收：桌面三栏不变；移动端抽屉可开关、可键盘操作且不遮挡阅读区。

### P1-06 Wiki 内容增强

- 覆盖：`WIKI-CONTENT-P1-01..03`。
- 实现：`section_kind` 专用 facts/table 映射；block 内 link spans；低质量 block 审计报告。
- 验收：确定性构建测试、关键词多 span 跳转测试、create-new 报告测试。

### P1-07 文本与多图舞台

- 覆盖：`WIKI-TEXT-P1-01`、`TILT-P1-01`。
- 实现：页面类型揭示参数；多图焦点切换保持稳定舞台尺寸。
- 验收：profile 测试、焦点图键盘切换和无布局位移测试。

### P1-08 媒体运维

- 覆盖：`MEDIA-P1-01..02`。
- 实现：完整 manifest 存在性只读审计；缩略图生成与显式映射工具，写入独立 `reverse1999/wiki-thumbnail/` 前缀。
- 验收：默认 dry-run；碰撞拒绝；无显式 `--apply` 时 MinIO 零写入；映射原子写入且不修改 `media_assets.jsonl`。

### P1-09 最终回归

- 完整前端、后端、构建和 Playwright。
- 真实 MySQL/API 页面与媒体检查。
- 重新生成 MinIO/Milvus 证据；除经批准的缩略图前缀外必须等值。
- 输出 `eval/wiki-reactbits-p1/spec-coverage.md` 与 `acceptance-summary.json`；每个 P1 ID 必须有代码、测试和证据。

## 完成规则

任一检查点缺少自动测试或真实证据均保持未完成。P2 不纳入本计划。
