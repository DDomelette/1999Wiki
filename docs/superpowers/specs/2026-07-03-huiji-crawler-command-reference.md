# 灰机 Wiki 重返未来 1999 爬虫命令索引

日期：2026-07-03
项目：`1999Search`
范围：只用于 `https://res1999.huijiwiki.com/wiki` 及其 API、静态资源数据。

## 使用前提

所有命令都在项目根目录执行：

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda activate 1999wiki
```

默认输出目录：

```text
D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999
```

默认账号校验：

```text
POTATO BOT
```

爬虫只做只读操作，不对 Wiki 执行编辑、上传、删除、移动、清缓存等写入动作。

## 正文和资源清单爬虫

启动脚本：

```powershell
.\crawl_huiji_res1999.bat
```

底层入口：

```powershell
.\crawl_huiji_res1999.ps1
python scripts\crawl_huiji_res1999.py
```

推荐使用 `.bat`，因为它会自动定位项目目录并调用 `1999wiki` conda 环境里的 Python。

### DryRun：会话和账号检查

```powershell
.\crawl_huiji_res1999.bat -Mode DryRun -Transport Edge -EdgePort 9333
```

功能：

- 打开或复用 Edge 爬虫专用会话。
- 等待人工完成灰机 Wiki / Cloudflare 验证。
- 调用只读 `userinfo` 和站点信息接口。
- 校验当前账号是否为 `POTATO BOT`。
- 不抓取页面正文，不下载资源。

用途：

- 首次运行前检查环境。
- Cookie 或验证过期后确认是否恢复。
- 排查账号是否误用个人账号。

### Small：小规模测试抓取

```powershell
.\crawl_huiji_res1999.bat -Mode Small -Transport Edge -EdgePort 9333
```

功能：

- 执行完整流程的小样本版本。
- 默认抓取最多 `20` 个候选正文页面。
- 同时扫描文件命名空间，生成资源 manifest 占位。
- 写入 `pages.jsonl`、`wikitext.jsonl`、`resources_manifest.jsonl` 和 `crawl_state.sqlite`。

调整样本数量：

```powershell
.\crawl_huiji_res1999.bat -Mode Small -Transport Edge -EdgePort 9333 -Limit 100
```

用途：

- 验证输出结构是否正常。
- 验证断点续跑和跳过未变化页面是否正常。
- 在 Full 前做低风险试跑。

### Full：完整正文和资源清单抓取

```powershell
.\crawl_huiji_res1999.bat -Mode Full -Transport Edge -EdgePort 9333
```

功能：

- 抓取目标命名空间的当前版本正文。
- 默认命名空间：`0,3500,10,828,14`。
- 扫描文件命名空间并生成资源 manifest 占位。
- 使用 `crawl_state.sqlite` 断点续跑。
- 根据远端 `lastrevid` 跳过已经抓过且未更新的页面。
- 不下载图片、音频、视频等二进制资源。

用途：

- 首次完整建立本地 Wiki 原始文本数据。
- 后续增量更新 Wiki 文本和资源清单。

已完成过的一次 Full 结果示例：

```json
{
  "account": "POTATO BOT",
  "dry_run": false,
  "fetch_candidates": 79032,
  "fetched_revisions": 79032,
  "indexed_pages": 79053,
  "namespaces": [0, 3500, 10, 828, 14],
  "resources_indexed": 61087
}
```

### Requests / Browser / Edge 三种传输方式

`-Transport Requests`

```powershell
.\crawl_huiji_res1999.bat -Mode DryRun -Transport Requests
```

功能：

- 直接用 Python HTTP 请求访问 MediaWiki API。
- Cookie 来源为灰机 Wiki bot 工具目录。
- 如果 Cloudflare 拦截直接请求，会失败并提示刷新 Cookie。

适用场景：

- Cloudflare 未拦截 Python 请求时最快。
- 依赖 `D:\1999WIKI_ROBOT` 下的 bot 工具 Cookie。

`-Transport Browser`

```powershell
.\crawl_huiji_res1999.bat -Mode DryRun -Transport Browser
```

功能：

- 使用 Playwright Chromium 的持久化浏览器上下文。
- 人工完成验证后，通过浏览器上下文发起只读 API 请求。

适用场景：

- 需要浏览器会话，但不想使用系统 Edge。
- 需要先安装 Playwright。

`-Transport Edge`

```powershell
.\crawl_huiji_res1999.bat -Mode DryRun -Transport Edge -EdgePort 9333
```

功能：

- 启动独立 Edge 窗口并开放本地调试端口。
- 人工登录或验证后，通过 Edge 页面上下文发起只读 API 请求。
- 会校验浏览器 API 返回账号是否为 `POTATO BOT`。

适用场景：

- 当前推荐方式。
- 适合 Cloudflare 要求真实浏览器验证时使用。

### 常用参数

`-Mode DryRun|Small|Full`

- `DryRun`：只检查环境、账号和 API 可访问性。
- `Small`：小规模测试抓取，默认 `20` 条正文候选。
- `Full`：完整抓取正文和资源 manifest。

`-Transport Requests|Browser|Edge`

- `Requests`：直接 HTTP 请求。
- `Browser`：Playwright 浏览器。
- `Edge`：Microsoft Edge 浏览器。

`-Limit N`

- Small 模式下限制正文抓取数量。
- 示例：`-Limit 100`。

`-Out PATH`

- 指定输出目录。
- 默认：`data\huiji\res1999`。

`-Namespaces "0,3500,10,828,14"`

- 指定正文抓取命名空间。
- 默认覆盖主条目、Data、模板、模块、分类。

`-ExpectedUser "POTATO BOT"`

- 指定必须匹配的登录账号。
- 如果 API 返回账号不是该值，爬虫会停止。

`-LogEvery 100`

- 每处理多少条打印一次进度。

`-Sleep 1.0`

- API 请求间隔，单位秒。
- 遇到风控风险时可以调大。

`-Force`

- 即使 `lastrevid` 未变化，也重新抓取候选页面。
- 一般不需要，除非怀疑本地输出损坏。

`-NoOpenBrowser`

- Requests 模式会话失效时不自动打开浏览器辅助刷新页面。

`-NoRetryOnSessionExpired`

- 会话或 Cloudflare 失效时直接退出，不在脚本中等待重试。

## 资源下载器

启动脚本：

```powershell
.\download_huiji_resources.bat
```

底层入口：

```powershell
.\download_huiji_resources.ps1
python scripts\download_huiji_resources.py
```

资源下载器读取 `crawl_state.sqlite` 的 `resources` 表，不依赖重新访问 Wiki API。它下载的是资源 manifest 里已经记录好的静态文件 URL。

默认资源保存位置：

```text
data\huiji\res1999\assets\files\<sha1>\<filename>
```

### 下载全部未完成资源

```powershell
.\download_huiji_resources.bat -Workers 2
```

功能：

- 下载所有 `download_status` 不是 `downloaded` 的资源。
- 已经校验完成的文件会跳过。
- 使用 `.part` 临时文件，下载完成并通过大小和 sha1 校验后才写入最终文件。
- 每个文件完成后更新 SQLite 状态。

用途：

- 首次下载图片、音频、视频等二进制资源。
- 中断后继续下载剩余资源。

### 单线程重试失败资源

```powershell
.\download_huiji_resources.bat -Workers 1 -IncludeFailed
```

功能：

- 重新处理 `download_status = failed` 的资源。
- 单线程可降低临时内存和网络波动导致的失败概率。

用途：

- 完整下载后只剩少量失败项时使用。
- 例如退出提示 `Re-run with -IncludeFailed to retry failed resources`。

### 限量测试下载

```powershell
.\download_huiji_resources.bat -Workers 2 -Limit 10
```

功能：

- 只下载前 `10` 个待处理资源。

用途：

- 测试下载器是否能写入文件。
- 检查网络和 CDN 连通性。

### 按 MIME 类型下载

只下载图片：

```powershell
.\download_huiji_resources.bat -Workers 2 -MimePrefix image/
```

只下载音频：

```powershell
.\download_huiji_resources.bat -Workers 2 -MimePrefix audio/
```

功能：

- 根据资源 manifest 中的 `mime` 前缀过滤下载任务。

用途：

- 分阶段下载资源。
- 优先下载图片，后续再下载音频或其他类型。

### 常用参数

`-Workers 2`

- 并发下载线程数。
- 默认 `2`。
- 保守建议 `1` 到 `3`，不建议大并发压站点 CDN。

`-IncludeFailed`

- 把之前失败的资源重新纳入下载队列。

`-Limit N`

- 限制本次处理资源数量。

`-Out PATH`

- 指定资源状态库和输出目录。
- 默认：`data\huiji\res1999`。

`-LogEvery 100`

- 每处理多少个资源打印一次进度。

`-Sleep 0.2`

- 每个 worker 下载间隔，单位秒。

`-Retries 2`

- 单个资源失败后的重试次数。

`-Timeout 30.0`

- 单次 HTTP 请求超时时间，单位秒。

`-MimePrefix image/`

- 只处理 MIME 前缀匹配的资源。
- 可重复传入多个前缀。

## 中断和续跑

正文爬虫：

- 可以用 `Ctrl+C` 中断。
- 下次执行同一命令会通过 `--resume` 和 `crawl_state.sqlite` 继续。
- 已抓且 `lastrevid` 未变化的页面会跳过。

资源下载器：

- 可以用 `Ctrl+C` 中断。
- 如果 `Ctrl+C` 无法退出，可以直接关闭正在运行命令的 PowerShell 窗口。
- 已完成并校验过的资源不会重下。
- 最多留下当前正在下载的 `.part` 临时文件。
- 下次执行同一下载命令会继续剩余资源。

停止后台资源下载进程：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*download_huiji_resources.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId }
```

## 输出文件速查

`siteinfo.json`

- 站点信息、命名空间信息和本次采集元数据。

`pages.jsonl`

- 页面索引记录。

`wikitext.jsonl`

- 当前版本 Wiki 源码。

`resources_manifest.jsonl`

- 图片、音频、视频等文件资源占位信息。

`crawl_state.sqlite`

- 长期断点续跑和增量更新状态库。

`errors.jsonl`

- 正文爬虫错误记录。

`resource_download_errors.jsonl`

- 资源下载失败记录。

`assets/files/<sha1>/<filename>`

- 已下载资源文件。

## 退出码含义

正文爬虫：

- `0`：成功。
- `1`：普通爬虫错误，例如参数错误、API 错误、账号不匹配。
- `2`：登录会话过期或 Cloudflare 验证拦截，需要人工刷新验证后续跑。

资源下载器：

- `0`：全部本次任务完成且没有失败。
- `1`：本次任务结束但仍有失败资源，通常用 `-IncludeFailed` 重试。

## 常见检索关键词

- 灰机 Wiki 爬虫命令
- res1999 爬虫
- POTATO BOT
- Edge 传输
- Cloudflare 验证
- DryRun
- Small
- Full
- 资源 manifest
- 资源下载器
- IncludeFailed
- 断点续跑
- crawl_state.sqlite
