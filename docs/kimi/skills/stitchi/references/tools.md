# Stitch MCP 工具清单（15 个）

> 来源：`stitch_mcp.py list` 实时拉取（2026-07-17，协议 2025-03-26）。
> 完整 `inputSchema`/`outputSchema` 以 `list` 实时返回为准，调用前先查 schema。

## 项目管理

| 工具 | 必填参数 | 用途 |
|---|---|---|
| `create_project` | 无 | 创建 Stitch 项目（UI 设计与前端代码的容器） |
| `get_project` | `name` | 获取项目详情 |
| `list_projects` | 无 | 列出可访问的项目 |
| `delete_project` | `name` | 删除项目（**破坏性，须用户明确确认**） |

## 屏幕（Screen）

| 工具 | 必填参数 | 用途 |
|---|---|---|
| `list_screens` | `projectId` | 列出项目内全部屏幕 |
| `get_screen` | `name`, `projectId`, `screenId` | 获取单个屏幕详情 |
| `generate_screen_from_text` | `projectId`, `prompt` | 按文本提示生成新屏幕 |
| `edit_screens` | `projectId`, `selectedScreenIds`, `prompt` | 按提示编辑已有屏幕 |
| `generate_variants` | `projectId`, `selectedScreenIds`, `prompt`, `variantOptions` | 生成已有屏幕的变体 |

## 设计系统（Design System）

| 工具 | 必填参数 | 用途 |
|---|---|---|
| `upload_design_md` | `projectId`, `designMdBase64` | 上传 DESIGN.md 到项目（base64 编码） |
| `create_design_system` | `designSystem` | 创建设计系统（整体视觉风格） |
| `create_design_system_from_design_md` | `projectId`, `selectedScreenInstance` | 基于已上传 DESIGN.md 创建并展示设计系统 |
| `update_design_system` | `name`, `projectId`, `designSystem` | 更新设计系统 |
| `list_design_systems` | 无 | 列出设计系统 |
| `apply_design_system` | `projectId`, `selectedScreenInstances`, `assetId` | 把设计系统应用到一批屏幕 |

## 典型调用顺序

1. `create_project` → 拿到 `projectId`
2. `generate_screen_from_text`（可多次）→ 生成屏幕
3. 可选：`create_design_system` / `apply_design_system` 统一视觉
4. `edit_screens` / `generate_variants` 迭代
5. `get_screen` 取回产物（图片/HTML 等，保存到工作区后再展示）
