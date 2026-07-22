# Huiji Crawler Windows Tool Documentation

本目录只保存灰机 Wiki 爬虫 Windows 工具的设计与执行计划。它不保存 Cookie、浏览器 profile、抓取数据、构建产物或验收日志。

## 文档结构

```text
docs/huiji-crawler/
├─ specs/   长期架构、模块契约和验收边界
└─ plans/   分阶段执行步骤和强制验收门槛
```

## 实施顺序

1. [P1 Windows 可迁移工具设计](specs/2026-07-20-windows-crawler-p1-portable-tool-design.md)
2. [P2 Windows 凭据生命周期设计](specs/2026-07-20-windows-crawler-p2-credential-lifecycle-design.md)
3. [P2 Windows 自包含离线分发设计](specs/2026-07-20-windows-crawler-p2-offline-distribution-design.md)

当前执行计划：[P1 Windows 可迁移工具实施计划](plans/2026-07-20-windows-crawler-p1-portable-tool.md)。P1 实现、标准包构建、四路径搬迁、真实 Edge 刷新、真实 Requests 只读验证和专项回归已经通过；最终完整测试复验正在等待并发 wiki v3 工作树恢复一致，尚未宣称 P1 最终完成。

每一阶段使用独立 plan、独立验收证据和独立完成判定。前一阶段未完成时，不激活后一阶段的运行时变更。

## 固定边界

- 仅支持 Windows x64，不建设 Linux 或 Docker 运行路径。
- 工具采用 CLI 与 `.cmd` 启动器，不建设 GUI。
- 抓取数据是可再生运行输出，不进入工具包。
- Cookie、`.env` 和 Browser/Edge profile 不进入任何分发包。
- 标准包与离线包必须运行同一份 crawler 源码。
- 目标机器通过本机 Edge 完成账号登录与凭据恢复。
