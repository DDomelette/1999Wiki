# Huiji Crawler Execution Plans

本目录保存灰机 Wiki crawler Windows 工具的分阶段执行计划。

计划必须从 `../specs/` 中对应规格的当前必需条目生成，并遵守以下顺序：

1. P1 portable tool。
2. P2 credential lifecycle。
3. P2 offline distribution。

前一阶段的全部硬验收未通过时，不得开始后一阶段运行时切换。计划不得包含 Cookie 值、`.local` 内容或抓取数据。

## 当前计划

- [P1 Windows 可迁移工具实施计划](2026-07-20-windows-crawler-p1-portable-tool.md)：Task 0-9 已完成并通过最终验收；下一阶段可开始 P2 credential lifecycle 的 implementation plan。
