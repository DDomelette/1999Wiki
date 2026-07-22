---
name: stitchi
description: Google Stitch MCP 服务器连接技能（HTTP 传输，端点 https://stitch.googleapis.com/mcp，请求头 X-Goog-Api-Key 取自环境变量 STITCH_API_KEY）。当用户希望用 Google Stitch 生成 UI 设计、界面稿、屏幕/原型图，或提到 Stitch / Stitchi / stitch.googleapis.com 时使用。提供连接验证、工具列表查询和工具调用的完整流程。
---

# Stitchi — Google Stitch MCP 连接

通过 `scripts/stitch_mcp.py`（纯 stdlib，无需安装依赖）以 MCP Streamable HTTP 协议调用 Stitch MCP 服务器。

## 连接事实

- 端点：`https://stitch.googleapis.com/mcp`（HTTP POST，JSON-RPC 2.0）
- 认证：请求头 `X-Goog-Api-Key`，值来自环境变量 `STITCH_API_KEY`
- 脚本自动处理：`initialize` 握手、`Mcp-Session-Id` 会话头复用、SSE（`text/event-stream`）响应解析
- Key 解析顺序：环境变量 → 当前工作目录 `.env` 文件中的 `STITCH_API_KEY=...`

## 工作流

1. **验证连通性**（首次使用或排错时）：

   ```bash
   python scripts/stitch_mcp.py ping
   ```

   输出 `serverInfo` 即认证成功。HTTP 401/403 说明 key 缺失或无效。

2. **查看可用工具**：

   ```bash
   python scripts/stitch_mcp.py list
   ```

   返回工具数组（名称、description、inputSchema）。调用前必读各工具的 `inputSchema`，按 schema 组装参数。
   15 个工具的参数速查与典型调用顺序见 [references/tools.md](references/tools.md)；完整 schema 以实时返回为准。

3. **调用工具**：

   ```bash
   python scripts/stitch_mcp.py call <tool_name> '{"param": "value"}'
   ```

   第二个参数必须是 JSON 对象字符串。结果中 `result.content` 为 MCP 内容块列表（text / image / resource 等）。

## 使用注意

- 所有成功输出为 stdout 上的 JSON（含 `"ok": true`）；诊断信息在 stderr；退出码 0 成功、2 缺 key 或用法错误、1 传输/协议错误。
- Stitch 生成的图片/资源若以 URL 或 base64 返回，先保存到工作区再展示给用户。
- 不要把 API key 打印到输出或写入任何文件。
- 网络失败优先重试一次；连续失败则报告原始错误，不要编造工具结果。
