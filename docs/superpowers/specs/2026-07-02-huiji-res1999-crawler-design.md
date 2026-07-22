# 灰机 Wiki 重返未来 1999 爬虫设计

日期：2026-07-02
项目：`1999Search`
目标 Wiki：`https://res1999.huijiwiki.com/wiki`
目标 API：`https://res1999.huijiwiki.com/api.php`

## 概要

本设计用于构建一个只读、API 优先的重返未来 1999 灰机 Wiki 采集器。采集器负责保存当前页面源码、`Data:` 命名空间的结构化 JSON、模板/模块/分类依赖，以及图片、视频、音频等文件资源的 manifest 占位。

第一版不下载二进制资源，也不抓历史版本。目标是先建立一个稳定、可恢复、可增量更新的本地数据底座，后续再基于这些原始数据做 RAG 清洗、资源下载和索引构建。

## 目标

- 只采集 `res1999.huijiwiki.com` 的数据。
- 使用 MediaWiki API，不抓渲染后的网页 HTML 作为主流程。
- 保持只读。默认 API 调用限制为 `action=query`。
- 保存目标命名空间的当前页面源码。
- 单独保存 `Data:` 命名空间页面，方便后续 JSON 解析。
- 为图片、视频、音频等文件资源保存 manifest 占位和稳定本地路径。
- 支持中断、Cloudflare cookie 过期、网络错误、限流后的断点续跑。
- 支持增量更新：通过远端 `lastrevid` 与本地状态对比，跳过未变化页面。
- 保持原始采集与后续 RAG 归一化解耦。

## 非目标

- 不执行任何写入动作，包括 `edit`、`upload`、`delete`、`move`、`purge`，以及任何会改变 Wiki 状态的 API。
- 不采集其他灰机 Wiki 站点。
- 第一版不采集讨论页、用户页、历史版本或其他无关命名空间。
- 第一版不下载图片、视频、音频等二进制文件。
- 不自动绕过 CAPTCHA 或 Cloudflare 人工验证。
- 爬虫不直接做 embedding、向量索引或问答系统构建；这些属于后续阶段。

## 已确认上下文

当前 bot 账号在 cookie 有效时可以访问 API。账号具备普通用户级读取权限，也有写 API 权限，但本设计会在代码层明确阻止写 API 使用。

现有 cookie 来源：

`D:\1999WIKI_ROBOT\huijiwiki_bot_gui_v0.3.46\config.dat`

现有环境变量文件：

`D:\1999WIKI_ROBOT\.env`

`.env` 中包含账号密码，但爬虫日志和输出文件绝不能打印密码、cookie 或其他密钥值。账号密码只允许用于只读会话校验。若 Cloudflare 要求浏览器验证，爬虫不尝试绕过验证，而是停止并提示用户通过现有浏览器或灰机工具刷新 cookie 后再续跑。

截至 2026-07-02 检查时，目标站点规模大致如下：

- 站点统计总页面数：约 140,334
- 主命名空间页面：约 5,910
- 文件命名空间页面：约 61,112
- `Data` 命名空间页面：约 72,757
- 模板命名空间页面：约 288
- 分类命名空间页面：约 100
- 模块命名空间页面：约 75

当前账号观察到的 API 限制：

- `list=allpages` 单次最多返回 500 页。
- `prop=revisions` 单次最多请求 50 个 pageid。
- 不应假设账号拥有高限制 API 权限。

第一版预估存储规模：

- 原始 wikitext、`Data:` JSON、元数据、manifest 和日志通常是数百 MB 级。
- 后续用于 RAG 的清洗文本可能达到 1 到 2 GB，取决于抽取策略。
- 第一版不下载二进制资源。未来若下载全部文件资源，可能需要数十 GB。

## 选定方案

采用 API 优先的增量采集方案。

采集器只访问：

`https://res1999.huijiwiki.com/api.php`

默认页面采集命名空间：

- `0`：主词条页面
- `3500`：`Data` 页面
- `10`：模板
- `828`：模块
- `14`：分类

同时读取文件命名空间的资源元数据，仅用于生成资源占位：

- `6`：文件，manifest only

这个方案优于直接抓网页 HTML，因为它更容易限速、恢复、去重和增量更新，也更不依赖页面布局变化。它也比浏览器网页抓取更适合作为长期维护的数据采集底座。

## 输出目录

默认输出根目录：

`D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999`

建议输出文件：

- `siteinfo.json`：站点信息、命名空间信息、统计数据和爬虫元数据。
- `pages.jsonl`：页面索引记录。
- `wikitext.jsonl`：当前版本源码记录。
- `data_pages.jsonl`：`Data:` 页面 JSON 原文和解析状态。
- `resources_manifest.jsonl`：图片、视频、音频等文件资源占位。
- `errors.jsonl`：可恢复请求错误、解析错误和写入错误。
- `crawl_state.sqlite`：长期增量状态库。
- `runs/<run_id>/run.json`：单次运行配置和统计摘要。
- `runs/<run_id>/requests.jsonl`：可选的请求诊断日志，仅在详细日志模式开启时写入。

`state.json` 可以作为当前运行的临时断点文件，但长期跳过逻辑必须放在 SQLite 中。

## 页面记录结构

`pages.jsonl` 每行保存一个页面索引记录：

```json
{
  "site": "res1999",
  "pageid": 123,
  "ns": 0,
  "title": "Example",
  "lastrevid": 456,
  "length": 7890,
  "touched": "2026-07-02T00:00:00Z",
  "seen_at": "2026-07-02T00:00:00+08:00",
  "status": "active"
}
```

`wikitext.jsonl` 每行保存一个当前版本源码记录：

```json
{
  "site": "res1999",
  "pageid": 123,
  "ns": 0,
  "title": "Example",
  "revid": 456,
  "timestamp": "2026-07-02T00:00:00Z",
  "content_model": "wikitext",
  "content_format": "text/x-wiki",
  "content": "...",
  "fetched_at": "2026-07-02T00:00:00+08:00"
}
```

`data_pages.jsonl` 复用 `wikitext.jsonl` 的关键字段，并增加 JSON 解析状态：

```json
{
  "site": "res1999",
  "pageid": 123,
  "title": "Data:Example.json",
  "revid": 456,
  "json_valid": true,
  "json_error": null,
  "content": "{...}",
  "fetched_at": "2026-07-02T00:00:00+08:00"
}
```

## 资源 Manifest 结构

`resources_manifest.jsonl` 保存二进制文件的占位信息。第一版不下载实际文件。

```json
{
  "site": "res1999",
  "source": "huiji_file_namespace",
  "title": "File:Example.png",
  "name": "Example.png",
  "url": "https://...",
  "descriptionurl": "https://res1999.huijiwiki.com/wiki/File:Example.png",
  "mime": "image/png",
  "size": 123456,
  "width": 512,
  "height": 512,
  "sha1": "optional-if-api-provides-it",
  "timestamp": "2026-07-02T00:00:00Z",
  "local_relpath": "assets/files/<sha1-or-pageid>/Example.png",
  "download_status": "not_downloaded",
  "seen_at": "2026-07-02T00:00:00+08:00"
}
```

稳定的 `local_relpath` 是第一版设计的一部分。未来资源下载器只需要把文件写入同一路径并更新 `download_status`，不需要修改页面记录或 RAG 文档 ID。

## 增量更新设计

每次运行先对目标命名空间做轻量页面索引扫描。采集器将远端元数据与 `crawl_state.sqlite` 对比后决定是否抓正文。

判断规则：

- 本地没有 `pageid`：新页面，抓取当前版本。
- 本地已有 `pageid`，但 `lastrevid` 变化：页面已更新，重新抓取当前版本。
- 本地已有 `pageid`，且 `lastrevid` 未变化：跳过正文抓取。
- 本地有页面，但某次完整命名空间扫描中远端不存在：标记为 `missing`。
- `pageid` 不变但 `title` 变化：视为页面移动或改名；更新标题，只有 `lastrevid` 也变化时才抓正文。

建议 SQLite 表：

- `pages`：`pageid`、`ns`、`title`、`lastrevid`、`length`、`touched`、`status`、`first_seen_at`、`last_seen_at`、`last_fetched_at`。
- `revisions`：`revid`、`pageid`、`timestamp`、`content_sha256`、`stored_in`、`fetched_at`。
- `resources`：`name`、`title`、`url`、`mime`、`size`、`sha1`、`timestamp`、`local_relpath`、`download_status`、`last_seen_at`。
- `runs`：`run_id`、`started_at`、`finished_at`、`status`、`config_json`、`summary_json`。
- `errors`：`run_id`、`stage`、`pageid`、`title`、`error_type`、`message`、`created_at`、`retryable`。

SQLite 优于单个 JSON 状态文件，因为页面数量较大，增量判断需要索引查询，且中断后的部分进度需要可靠保存。

## 模块划分

`CookieLoader`

- 从 `config.dat` 读取 cookie。
- 仅在需要只读会话校验时读取 `.env`。
- 不记录 cookie、密码或密钥值。
- 对外暴露明确状态：cookie 有效、cookie 过期、cookie 缺失、Cloudflare 验证拦截。

`HuijiApiClient`

- 负责所有 API 请求。
- 固定 API 主机为 `res1999.huijiwiki.com`。
- 强制执行 action 白名单。第一版生产采集只允许 `action=query`。
- 对临时错误执行重试和退避。
- 检测“期望 JSON 但实际返回 HTML 验证页”的情况。

`PageEnumerator`

- 使用 `list=allpages`、`apnamespace`、`aplimit=500` 扫描页面。
- 写入页面索引记录并更新 SQLite 状态。
- 写入命名空间扫描完成标记，避免在未完整扫描时误判页面缺失。

`RevisionFetcher`

- 使用 `prop=revisions`，每批最多 50 个 pageid。
- 只抓当前版本，不抓历史版本。
- 先把原始内容写入 JSONL，再把该 revision 标记为已抓取。

`ResourceManifestBuilder`

- 通过文件命名空间或图片列表 API 收集文件元数据。
- 只生成资源占位。
- 不下载二进制文件。

`OutputWriter`

- 使用追加式 JSONL 写入。
- 定期 flush。
- 为内容计算 hash，用于去重和完整性检查。

`CrawlStateStore`

- 封装 SQLite 读写。
- 基于 `pageid` 和 `lastrevid` 给出跳过或抓取决策。
- 保存运行摘要和失败详情。

`Normalizer`

- 不属于第一版爬虫实现。
- 后续负责把原始 Wiki 数据转换为当前 `1999Search` RAG 使用的 `documents.jsonl`。

## 运行流程

1. 加载配置和 cookie。
2. 用只读 query 校验 API 可访问。
3. 抓取 `siteinfo`。
4. 扫描选定页面命名空间并更新页面状态。
5. 根据新增或变化的 `lastrevid` 计算待抓页面集合。
6. 按最多 50 个 pageid 一批抓取当前版本源码。
7. 写入 wikitext 记录和 `Data:` JSON 记录。
8. 扫描文件元数据并写入资源 manifest 占位。
9. 在 SQLite 中标记命名空间扫描完成和本次运行摘要。

如果运行中断，下一次使用 `--resume` 时从 SQLite 状态和 JSONL 输出继续。

## CLI 形态

默认命令：

```powershell
conda run -n 1999wiki python 1999Search\scripts\crawl_huiji_res1999.py `
  --robot-root D:\1999WIKI_ROBOT `
  --out 1999Search\data\huiji\res1999 `
  --namespaces 0,3500,10,828,14 `
  --include-file-manifest `
  --sleep 1.0 `
  --resume
```

常用参数：

- `--dry-run`：校验 cookie、API 访问、命名空间数量和输出路径，不抓页面正文。
- `--limit N`：测试时最多抓 N 个变化页面。
- `--namespaces 0,3500,10,828,14`：选择命名空间。
- `--include-file-manifest`：生成文件资源占位。
- `--resume`：使用 `crawl_state.sqlite` 续跑并跳过未变化页面。
- `--force`：即使 `lastrevid` 未变化也重新抓取选定页面。
- `--sleep 1.0`：API 请求间隔。
- `--max-retries 5`：临时错误最大重试次数。

## 错误处理

临时网络错误：

- 使用指数退避重试。
- 将失败记录到 `errors.jsonl` 和 SQLite。
- 在安全情况下继续运行。

限流或服务器过载：

- 对 `429`、`502`、`503`、`504` 执行退避。
- 默认保持单请求流，不并发压测。

Cloudflare 或登录失效：

- 检测 HTTP `403`、验证 HTML、或 API 期望 JSON 但返回非 JSON。
- 快速停止，不做密集重试。
- 提示用户通过浏览器或现有灰机工具刷新 cookie。
- cookie 刷新后使用同一命令续跑。

解析失败：

- 仍然保存原始内容。
- 对无效 `Data:` JSON 标记 `json_valid=false`。
- 将解析错误与请求错误分开记录。

写入失败：

- 先写内容，再在 SQLite 中标记已抓。
- 使用 JSONL，避免单条失败破坏整个数据集。

## 速率与风险控制

默认运行策略保守：

- 单进程。
- 单请求流。
- 请求间隔默认 `sleep=1.0` 秒。
- 页面列表单批 500。
- revision 单批 50。
- 遇到 Cloudflare 验证立即停止。
- 不抓渲染 HTML 页面。
- 不下载二进制文件。

该策略的风控风险低于浏览器页面抓取，但不能完全避免 Cloudflare cookie 过期或临时限流。

## 许可与署名

目标 Wiki 页面标注了 `CC BY-NC-SA 3.0` 共享协议。当前项目为个人非商业用途，但下游生成物仍应保留来源 URL、页面标题、revision ID 和时间戳，方便后续处理署名和相同方式共享要求。

爬虫应保存以下元数据：

- `site`
- `title`
- `pageid`
- `revid`
- `source_url`
- `timestamp`
- `fetched_at`

## 测试与验证

完整采集前先做小规模验证：

- 运行 `--dry-run`，验证 cookie 读取、host 锁定、siteinfo 和命名空间访问。
- 对 `0,3500` 命名空间运行 `--limit 20`，检查输出结构。
- 再运行一次 `--limit 20 --resume`，验证未变化页面会被跳过。
- 测试无效或过期 cookie，确认爬虫停止且不会重复请求。

自动化测试应覆盖：

- 只读 API action guard 会拒绝写操作。
- API host guard 会拒绝非 `res1999.huijiwiki.com` URL。
- SQLite 增量逻辑能处理新页面、未变化页面、变化页面、改名页面和缺失页面。
- JSONL writer 能追加有效记录。
- 资源 manifest 的本地路径生成稳定。
- Cloudflare HTML 响应会被识别为会话问题。

## 验收标准

- 爬虫可以使用现有 cookie 文件对 `res1999.huijiwiki.com` 完成 dry run。
- 爬虫会写入 `siteinfo.json`、`pages.jsonl`、`wikitext.jsonl`、`data_pages.jsonl`、`resources_manifest.jsonl`、`errors.jsonl` 和 `crawl_state.sqlite`。
- 续跑时会跳过 `lastrevid` 未变化的页面。
- 当 `lastrevid` 变化时，对应页面会重新抓取。
- 资源 manifest 包含稳定本地占位路径，但不会下载二进制内容。
- 实现中包含硬性的只读保护和目标 host 保护。
- Cloudflare 或登录失效时会停止并给出明确提示，不进行密集重试。
- 日志和输出文件不会写入账号密码、cookie 值或疑似密钥字符串。

## 实现边界

本规格只覆盖爬虫数据底座。规格审核通过后，下一步是编写 implementation plan。计划应聚焦爬虫构建、测试和小规模验证运行。RAG 归一化与二进制资源下载应作为后续工作单独规划。
