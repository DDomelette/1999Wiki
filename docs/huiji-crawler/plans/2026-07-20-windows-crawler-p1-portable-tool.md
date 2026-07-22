# Windows Huiji Crawler P1 Portable Tool Implementation Plan

> **执行方式：** 使用 `superpowers:executing-plans` 在当前线程逐任务执行。默认不使用子代理，不创建 worktree，不执行 Git staging、commit、reset、checkout 或 clean。每个任务必须完成 RED、GREEN、邻接回归与任务自检后才能进入下一任务。

日期：2026-07-20  
状态：Task 0-8 已完成；Task 9 专项验收通过，最终完整测试复验被并发 wiki v3 中间态阻断  
对应规格：[2026-07-20-windows-crawler-p1-portable-tool-design.md](../specs/2026-07-20-windows-crawler-p1-portable-tool-design.md)

**目标：** 把现有灰机 Wiki crawler 收束为一个仅支持 Windows x64、使用系统 CPython 3.12 安装依赖、可整体搬迁、无 GUI、无外部项目路径依赖的标准工具包，同时保留 `src/huijiwiki` 作为唯一业务实现。

**架构：** 新增 `src/huiji_crawler_tool` 作为工具入口、配置、路径边界、运行锁、诊断和结构化审计层；`src/huijiwiki` 继续负责只读抓取。构建端依据显式 allowlist 生成 crawler-only staging、canonical manifest、CycloneDX SBOM、许可材料与确定性 ZIP。目标机通过 `install.cmd` 在工具根内创建 `.venv`，通过 `huiji-crawler.cmd` 运行统一 CLI。

**技术栈：** Windows PowerShell 5.1+、CMD、CPython `>=3.12.0,<3.13` x64、pytest、PyYAML、requests、Playwright、Python AST、PowerShell AST、SHA-256、ZIP、CycloneDX JSON。

## 0. 当前执行状态

- Task 0 至 Task 8 已完成；R2 双构建 ZIP、tree、manifest、SBOM 和 receipt 一致，独立解压 full verification 通过。
- Task 9 Step 1 至 Step 6 已完成；普通路径、空格路径、中文路径和跨盘路径的安装、doctor、fail-closed、路径审计与 containment 全部通过。
- 中文路径已完成真实 Edge refresh，账号为 `POTATO BOT`；真实 Requests dry-run 观测到 2 个 `GET + action=query` 请求，非只读动作和旧根访问均为 0。
- 专项回归为 `120 passed`，source path audit 扫描 38 个文件且所有异常计数为 0。
- 发布候选为 `dist/huiji-crawler/p1-a-r2/huiji-crawler-windows-standard.zip`，SHA-256 为 `7b209a11957ceb929cd4c8bf6bb37ec355a57e90b31761aef38d8b117cde88d8`。
- Task 9 Step 7 与 Step 8 暂未关闭：并发 wiki v3 线路已经加入测试，但 `src/huiji_wiki/media_v3.py` 尚未落盘，且 `snapshot.py` 尚未接受 v3 active pointer。该范围不属于本计划，不在此线路修复；完整套件恢复绿色后才生成最终 `final-acceptance.v1.json` 并宣称 P1 完成。

## 1. 本轮范围

本轮必须完成规格中的全部当前必需条目：

- `CLI-P0-01` 至 `CLI-P0-05`
- `CONFIG-P0-01` 至 `CONFIG-P0-07`
- `CREDENTIAL-P0-01` 至 `CREDENTIAL-P0-07`
- `PACKAGE-P0-01` 至 `PACKAGE-P0-10`
- `DISCOVERY-P0-01` 至 `DISCOVERY-P0-03`
- `AUDIT-P0-01` 至 `AUDIT-P0-04`

本轮还必须落实规格第 8、9 节中的稳定退出码、前置门禁、搬迁矩阵和真实 transport 验收。以上均为本阶段硬指标，不能用占位实现或仅有 mock 的测试替代。

## 2. 明确不做

- 不实现 DPAPI、多账号、计划任务、自动提醒或凭据跨用户迁移；这些属于 P2 credential lifecycle。
- 不嵌入 Python、不携带 wheelhouse、不制作完全离线 ZIP；这些属于 P2 offline distribution。
- 不支持 Linux、macOS、Docker、GUI、托盘或后台常驻服务。
- 不把抓取结果、Cookie、`.env`、浏览器 profile、日志、数据库、RAG、Milvus、MinIO、后端或前端放入工具包。
- 不修改或清理现有 `data/**`、Milvus、MinIO、MySQL、Docker volume 和已存在的抓取产物。
- 不删除或改写旧凭据源；只允许读取、取证和显式迁移到新的 canonical 目标。
- 不执行 Git 操作；当前脏工作树中的非本任务改动必须原样保留。

## 3. 全局约束

- 开发与测试解释器固定使用 `D:\Anaconda32024\envs\langchain\python.exe`；它是 CPython 3.12 x64。现有 `1999wiki` Python 3.11 仅用于基线对照，不作为标准包目标运行时。
- 标准包的直接依赖固定从当前已验证版本起步：`requests==2.34.2`、`PyYAML==6.0.3`、`playwright==1.61.0`。传递依赖必须由目标为 CPython 3.12/win_amd64 的 lock 生成器解析并记录发行文件 SHA-256。
- 工具根是唯一项目状态边界。`.local`、`.venv`、`workspace`、配置、日志、状态数据库、锁和浏览器 profile 全部必须在工具根内。
- 系统 Edge executable 是唯一允许位于工具根外的文件依赖。URL、loopback CDP endpoint 和 Python 注册启动器不是项目数据路径。
- 工具持有路径使用 `Path.resolve()` 后的真实路径 containment；字符串前缀判断不算实现。symlink 或 junction 解析后越界必须停止。
- 任一前置门禁失败时，不启动 Edge、不访问灰机 API、不创建 `workspace` 抓取文件。
- 抓取链路继续只允许灰机 Wiki 只读 API action；不得放宽现有 read-only 和 host guard。
- 所有 JSON 证据使用 UTF-8、键排序、紧凑分隔符和结尾换行；报告不得写入 Cookie 值、完整 Cookie header 或凭据正文。
- 构建和验收生成物进入 `dist/huiji-crawler/**` 或 `eval/huiji-crawler/**`，不进入源码 allowlist。
- 若任务修改了共享 crawler 行为，除任务局部测试外必须运行全部 `tests/test_huiji_*` 邻接测试；最终必须运行完整 Python 测试套件。

## 4. 目标目录与核心接口

### 4.1 源码目录

```text
src/huijiwiki/                 唯一 crawler 业务实现
src/huiji_crawler_tool/        CLI、配置、边界、锁、诊断、审计
src/huiji_crawler_packaging/   构建端专用，不进入标准工具包
bootstrap/                     仅依赖 stdlib 的安装与 package verification
packaging/huiji-crawler/       allowlist、依赖输入、模板和构建策略
config/crawler.yaml            crawler-only 非敏感配置
```

### 4.2 标准包运行目录

```text
<tool-root>/
├─ bootstrap/
├─ config/crawler.yaml
├─ src/huijiwiki/
├─ src/huiji_crawler_tool/
├─ requirements-crawler.in
├─ requirements-crawler.lock.txt
├─ huiji-crawler.cmd
├─ install.cmd
├─ verify-package.cmd
├─ bootstrap/select-python.cmd
├─ README.md
├─ package-manifest.v1.json
├─ package-manifest.v1.sha256
├─ sbom.cdx.json
├─ THIRD_PARTY_NOTICES.json
├─ THIRD_PARTY_LICENSES/
├─ .venv/                         安装后创建，不在 ZIP
├─ .local/accounts/default/       运行后创建，不在 ZIP
└─ workspace/default/res1999/     抓取后创建，不在 ZIP
```

### 4.3 固定运行路径

```text
credential       .local/accounts/default/credential.json
browser profile  .local/accounts/default/browser-profile
edge profile     .local/accounts/default/edge-profile
refresh runtime  .local/accounts/default/refresh-runtime
runtime lock     .local/locks/default.lock
default output   workspace/default/res1999
```

### 4.4 稳定退出码

| Code | 含义 | 代表异常 |
|---:|---|---|
| 0 | 成功 | 命令完成或 `--help` |
| 1 | 未分类内部错误 | 仅用于未被领域异常覆盖的缺陷 |
| 2 | 凭据、登录、Cloudflare challenge | 缺失/过期/无效凭据、session expired |
| 3 | CLI、配置或路径边界 | 参数错误、YAML 错误、路径逃逸 |
| 4 | package 或依赖完整性 | manifest、hash、依赖 import 失败 |
| 5 | 网络或灰机 API | HTTP、API response、站点不可用 |
| 6 | 账号不匹配 | 实际账号不等于 `expected_user` |
| 7 | 运行锁冲突 | 同一 default workspace 已被占用 |
| 8 | Windows、Python 或 Edge 环境 | 不支持的平台/解释器/浏览器 |

## 5. Specs 覆盖矩阵

| Specs | 实施任务 | 自动测试 | 真实/包级验收 | 失败表现 |
|---|---|---|---|---|
| `CLI-P0-01..05` | Task 3、4、6 | CLI、wrapper、CMD 测试 | 四路径执行统一命令 | 稳定非零退出，stderr 无秘密 |
| `CONFIG-P0-01..07` | Task 1、3 | 优先级、路径、junction、脱敏测试 | 搬迁与 forbidden-root 运行 | API/Edge/workspace 前停止 |
| `CREDENTIAL-P0-01..07` | Task 2、3 | schema、legacy-only、原子写、冲突测试 | 一次真实 Edge refresh，旧源 hash 不变 | 目标保持原样或不创建 |
| `PACKAGE-P0-01..10` | Task 6、7、8 | allowlist、lock、manifest、determinism 测试 | 双构建同 hash、ZIP 全量验证 | 不生成可发布 ZIP |
| `DISCOVERY-P0-01..03` | Task 4、6 | Python/Edge 候选和 doctor 测试 | Python 3.12 x64 安装与系统 Edge | 安装/doctor 退出 8 |
| `AUDIT-P0-01..04` | Task 5、8 | AST/parser/YAML/JSON/path escape 测试 | staging 与四个解压根审计 | unclassified/stale 非零即阻断 |

---

## Task 0: 冻结基线与受保护对象

**对应 specs：** 全部条目的执行前置，不完成任何功能。

**读取：**

- `src/huijiwiki/**`
- `scripts/crawl_huiji_res1999.py`
- `scripts/import_huiji_credentials.py`
- `scripts/refresh_huiji_credentials.py`
- `crawl_huiji_res1999.ps1`
- `crawl_huiji_res1999.bat`
- `.local/huiji/credentials/config.dat`（仅当存在）

**创建证据：** `eval/huiji-crawler/<run-id>/p1/baseline/**`

- [ ] **Step 1: 建立唯一 evidence root，禁止覆盖**

```powershell
$Project = (Resolve-Path 'D:\PycharmProjects\nlp\LangChain\1999Search').Path
$Python = 'D:\Anaconda32024\envs\langchain\python.exe'
$RunId = Get-Date -Format 'yyyyMMdd-HHmmss'
$Evidence = Join-Path $Project "eval\huiji-crawler\$RunId\p1"
if (Test-Path -LiteralPath $Evidence) { throw "Evidence root already exists: $Evidence" }
New-Item -ItemType Directory -Path (Join-Path $Evidence 'baseline') -ErrorAction Stop | Out-Null
```

- [ ] **Step 2: 记录解释器、现有源和旧凭据源基线**

```powershell
& $Python -c "import json,platform,sys; print(json.dumps({'implementation':sys.implementation.name,'version':list(sys.version_info[:3]),'machine':platform.machine()},sort_keys=True))" | Set-Content -Encoding UTF8 (Join-Path $Evidence 'baseline\python.json')
Get-ChildItem -LiteralPath (Join-Path $Project 'src\huijiwiki') -File | Sort-Object Name | Get-FileHash -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 (Join-Path $Evidence 'baseline\huijiwiki-source-hashes.json')
$LegacyCredential = Join-Path $Project '.local\huiji\credentials\config.dat'
if (Test-Path -LiteralPath $LegacyCredential -PathType Leaf) {
    Get-Item -LiteralPath $LegacyCredential | Select-Object FullName,Length,LastWriteTimeUtc | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Evidence 'baseline\legacy-credential-file.json')
    Get-FileHash -LiteralPath $LegacyCredential -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Evidence 'baseline\legacy-credential-sha256.json')
}
```

证据中只记录旧凭据路径、size、mtime 和 SHA-256，不读取或输出 Cookie 值。

- [ ] **Step 3: 跑当前基线测试**

```powershell
& $Python -m pytest tests/test_huiji_cli.py tests/test_huiji_cookies.py tests/test_huiji_credential_store.py tests/test_huiji_credential_import_cli.py tests/test_huiji_credential_refresh.py tests/test_huiji_project_paths.py tests/test_runtime_path_audit.py tests/test_runtime_secret_audit.py tests/test_huiji_start_script.py tests/test_huiji_project_boundary_script.py -q
& $Python -m pytest -q
```

**通过门槛：** 两条命令均无失败；记录结果摘要。若基线因与本任务无关的现有改动失败，先定位并写入 `baseline/blockers.json`，不得通过放宽测试继续。

---

## Task 1: 建立工具根、crawler-only 配置和运行锁

**对应 specs：** `CONFIG-P0-01..07`，并实现退出码 3、7 的底层契约。

**文件：**

- Create: `src/huiji_crawler_tool/__init__.py`
- Create: `src/huiji_crawler_tool/errors.py`
- Create: `src/huiji_crawler_tool/runtime_paths.py`
- Create: `src/huiji_crawler_tool/config.py`
- Create: `src/huiji_crawler_tool/runtime_lock.py`
- Create: `config/crawler.yaml`
- Modify: `.gitignore`
- Create: `tests/test_huiji_crawler_tool_paths.py`
- Create: `tests/test_huiji_crawler_tool_config.py`
- Create: `tests/test_huiji_crawler_runtime_lock.py`

**稳定接口：**

```python
@dataclass(frozen=True)
class ToolPaths:
    root: Path
    settings_file: Path
    credential_file: Path
    workspace: Path
    browser_profile: Path
    edge_profile: Path
    refresh_runtime: Path
    lock_file: Path

    @classmethod
    def from_root(cls, root: Path) -> "ToolPaths": ...

def resolve_owned_path(value: str | Path, *, root: Path, label: str,
                       must_exist: bool = False) -> Path: ...

@dataclass(frozen=True)
class CrawlerSettings:
    paths: ToolPaths
    namespaces: tuple[int, ...]
    include_file_manifest: bool
    sleep: float
    expected_user: str
    progress: bool
    log_every: int
    transport: Literal["requests", "browser", "edge"]
    browser_headless: bool
    browser_verify: bool
    edge_port: int
    edge_executable: Path | None

def load_crawler_settings(*, tool_root: Path,
                          cli_overrides: Mapping[str, object] | None = None,
                          environ: Mapping[str, str] | None = None) -> CrawlerSettings: ...

class RuntimeLock:
    def __enter__(self) -> "RuntimeLock": ...
    def __exit__(self, ...) -> None: ...
```

`RuntimeLock` 使用 Windows `msvcrt.locking` 持有打开的 lock file；获取失败抛出 `RuntimeLockConflict`，不得删除其他进程的锁文件。

- [ ] **Step 1: 添加 RED 测试**

测试至少包括：

```python
def test_tool_paths_are_root_relative_and_fixed(): ...
def test_owned_path_rejects_absolute_parent_symlink_and_junction_escape(): ...
def test_edge_executable_is_the_only_external_file_path(): ...
def test_config_priority_is_cli_then_env_then_yaml_then_defaults(): ...
def test_config_rejects_unknown_keys_invalid_types_and_secret_fields(): ...
def test_config_error_does_not_create_local_workspace_or_profile(): ...
def test_runtime_lock_rejects_second_holder_and_releases_cleanly(): ...
```

- [ ] **Step 2: 运行 RED**

```powershell
& $Python -m pytest tests/test_huiji_crawler_tool_paths.py tests/test_huiji_crawler_tool_config.py tests/test_huiji_crawler_runtime_lock.py -q
```

Expected: 因新模块不存在而失败。

- [ ] **Step 3: 写入最小 `config/crawler.yaml`**

```yaml
schema_version: huiji_crawler_config.v1
site:
  expected_user: POTATO BOT
crawl:
  namespaces: [0, 3500, 10, 828, 14]
  include_file_manifest: false
  sleep_seconds: 1.0
  progress: true
  log_every: 100
  transport: requests
browser:
  headless: false
  verify_account: true
edge:
  port: 9222
```

所有拥有路径由 `ToolPaths` 固定生成，不从 YAML 读取任意路径。允许的环境变量精确为：

```text
HUIJI_CRAWLER_NAMESPACES
HUIJI_CRAWLER_INCLUDE_FILE_MANIFEST
HUIJI_CRAWLER_SLEEP
HUIJI_CRAWLER_EXPECTED_USER
HUIJI_CRAWLER_PROGRESS
HUIJI_CRAWLER_LOG_EVERY
HUIJI_CRAWLER_TRANSPORT
HUIJI_CRAWLER_BROWSER_HEADLESS
HUIJI_CRAWLER_BROWSER_VERIFY
HUIJI_CRAWLER_EDGE_PORT
HUIJI_CRAWLER_EDGE_EXECUTABLE
HUIJI_CRAWLER_OUT
HUIJI_CRAWLER_BROWSER_PROFILE
HUIJI_CRAWLER_EDGE_PROFILE
```

后三个 owned-path 覆盖仍必须解析在工具根内。`HUIJI_CRAWLER_EDGE_EXECUTABLE` 可位于工具根外，但必须是存在的文件。

- [ ] **Step 4: 实现真实路径 containment 与配置合并**

实现时先 `resolve(strict=False)`，再 `relative_to(root.resolve(strict=True))`。对尚不存在的路径也必须解析已有父目录中的 symlink/junction。YAML 顶层或分组出现未知 key 时 fail closed；布尔值不得使用 Python 的宽松真值转换。

在 `.gitignore` 增加：

```text
workspace/
dist/
```

- [ ] **Step 5: 运行 GREEN 与邻接回归**

```powershell
& $Python -m pytest tests/test_huiji_crawler_tool_paths.py tests/test_huiji_crawler_tool_config.py tests/test_huiji_crawler_runtime_lock.py tests/test_huiji_project_paths.py tests/test_config.py -q
& $Python -m compileall -q src/huiji_crawler_tool
```

**任务门槛：** 所有 path escape 在目录创建前失败；第二个锁持有者稳定映射到退出码 7 所用异常；配置和异常文本不含环境变量值或 Cookie 内容。

---

## Task 2: 收束 canonical 凭据并隔离 legacy decoder

**对应 specs：** `CREDENTIAL-P0-01..07`。

**文件：**

- Create: `src/huijiwiki/credential_schema.py`
- Create: `src/huijiwiki/legacy_credentials.py`
- Modify: `src/huijiwiki/cookies.py`
- Modify: `src/huijiwiki/client.py`
- Modify: `src/huijiwiki/credential_store.py`
- Modify: `src/huijiwiki/credential_refresh.py`
- Modify: `src/huijiwiki/crawler.py`
- Modify: `src/runtime_secret_audit.py`
- Modify: `tests/test_huiji_cookies.py`
- Modify: `tests/test_huiji_credential_store.py`
- Modify: `tests/test_huiji_credential_import_cli.py`
- Modify: `tests/test_huiji_credential_refresh.py`
- Modify: `tests/test_huiji_client.py`
- Modify: `tests/test_runtime_secret_audit.py`
- Create: `tests/test_huiji_credential_schema.py`
- Create: `tests/test_huiji_legacy_credentials.py`

**稳定接口与 schema：**

```python
CREDENTIAL_SCHEMA_VERSION = "huiji_credential.v2"

@dataclass(frozen=True)
class CredentialCookie:
    name: str
    value: str
    domain: str
    path: str
    expires: int | None
    secure: bool
    http_only: bool

@dataclass(frozen=True)
class CanonicalCredential:
    expected_user: str
    cookies: tuple[CredentialCookie, ...]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CanonicalCredential": ...
    def to_bytes(self) -> bytes: ...
    def to_requests_cookie_jar(self) -> RequestsCookieJar: ...
    def secret_values(self) -> tuple[tuple[str, str], ...]: ...
    def expires_at(self, name: str, *, host: str) -> int | None: ...

def decode_legacy_credential(raw: bytes, *, expected_user: str) -> CanonicalCredential: ...

def import_legacy_credential(source: Path, target: Path, *, expected_user: str,
                             replace: bool = False) -> dict[str, object]: ...
```

canonical payload 精确为：

```json
{
  "schema_version": "huiji_credential.v2",
  "expected_user": "POTATO BOT",
  "cookies": [
    {
      "name": "huiji_session",
      "value": "<private>",
      "domain": ".huijiwiki.com",
      "path": "/",
      "expires": null,
      "secure": true,
      "http_only": true
    }
  ]
}
```

- [ ] **Step 1: 将旧 loader 行为改写成 RED 断言**

新增或改写测试：

```python
def test_cookie_loader_accepts_only_exact_v2_schema(): ...
def test_cookie_loader_rejects_pickle_line_json_without_version_and_unknown_fields(): ...
def test_cookie_loader_reports_names_and_expiry_without_values(): ...
def test_canonical_credential_is_deterministic_and_rejects_duplicate_identity(): ...
def test_same_name_different_domain_or_path_is_preserved_in_requests_cookie_jar(): ...
def test_legacy_decoder_supports_pickle_line_and_unversioned_json_only_explicitly(): ...
def test_legacy_decoder_is_not_imported_by_cookies_module(): ...
def test_import_converts_to_v2_and_never_copies_source_bytes_verbatim(): ...
def test_import_same_canonical_payload_is_idempotent(): ...
def test_import_conflict_requires_replace_and_preserves_target(): ...
def test_import_replace_failure_preserves_target_and_removes_temp(): ...
def test_import_source_hash_size_and_mtime_are_unchanged(): ...
def test_refresh_writes_v2_directly_with_expected_user(): ...
```

- [ ] **Step 2: 运行 RED**

```powershell
& $Python -m pytest tests/test_huiji_credential_schema.py tests/test_huiji_legacy_credentials.py tests/test_huiji_cookies.py tests/test_huiji_credential_store.py tests/test_huiji_credential_refresh.py tests/test_huiji_client.py tests/test_runtime_secret_audit.py -q
```

Expected: 当前无版本 JSON、行格式和 pickle 仍被稳定 loader 接受，且 refresh 未写 schema，因此失败。

- [ ] **Step 3: 实现 strict canonical parser**

要求：

- 顶层 key、Cookie key、类型、domain、path、布尔和 expiry 全部严格校验。
- Cookie 按 `(name, domain, path)` 排序；只拒绝重复的完整 identity。同名但不同 domain/path 的 Cookie 必须保留，并通过 `RequestsCookieJar` 传给 `HuijiApiClient`，不得先压成 `dict` 静默覆盖。
- expiry 查询按目标 host 的 domain/path 适用性与 specificity 解析；不得因为其他 domain 的同名 Cookie 误判 `__cf_bm` 过期。
- `CookieLoader` 只调用 `CanonicalCredential.from_bytes()`；`src/huijiwiki/cookies.py` 中不得出现 `pickle` import、行格式解析或 legacy fallback。
- `describe()`、inspection、status 和错误文本只包含文件名、schema、hash、size、Cookie 名称和数量。

- [ ] **Step 4: 实现显式 legacy migration 与原子写**

`legacy_credentials.py` 是唯一可 import `pickle` 的生产模块。导入流程固定为：

```text
read source bytes
-> hash/size/mtime evidence
-> explicit legacy decode
-> canonical model validation
-> deterministic v2 bytes
-> inspect existing target
-> write temp + flush + fsync
-> re-read and parse temp
-> os.replace
-> re-read target
-> re-stat/re-hash source
-> redacted report
```

任一失败保持目标原样；源文件永不写入、移动或删除。报告 schema 升级为 `huiji_credential_import.v2`，source 与 target hash 不要求相同，因为目标是 canonical 转换结果。

- [ ] **Step 5: 让 browser refresh 直接生成 v2**

将接口改为：

```python
def serialize_huiji_cookies(raw_cookies: list[dict[str, object]], *,
                            expected_user: str) -> bytes: ...
```

Playwright 的 `httpOnly` 显式映射为 canonical `http_only`。账号验证必须先成功，之后才读取 Cookie 和替换目标。

- [ ] **Step 6: 运行 GREEN、静态隔离和邻接回归**

```powershell
& $Python -m pytest tests/test_huiji_credential_schema.py tests/test_huiji_legacy_credentials.py tests/test_huiji_cookies.py tests/test_huiji_credential_store.py tests/test_huiji_credential_import_cli.py tests/test_huiji_credential_refresh.py tests/test_huiji_client.py tests/test_runtime_secret_audit.py tests/test_huiji_cli.py -q
rg -n "import pickle|from pickle" src/huijiwiki
& $Python -m compileall -q src/huijiwiki
```

Expected: `rg` 只命中 `src/huijiwiki/legacy_credentials.py`；全部测试通过。

**任务门槛：** 不迁移真实旧凭据；本任务只完成代码与合成 fixture。真实 refresh 和旧源 hash 对照在 Task 9 执行。

---

## Task 3: 统一 CLI、前置门禁和兼容 wrapper

**对应 specs：** `CLI-P0-02..05`、`CONFIG-P0-02..07`，以及规格第 8 节完整数据流。

**文件：**

- Create: `src/huiji_crawler_tool/__main__.py`
- Create: `src/huiji_crawler_tool/cli.py`
- Modify: `src/huijiwiki/crawler.py`
- Modify: `src/huijiwiki/errors.py`
- Modify: `src/huijiwiki/browser_client.py`
- Modify: `scripts/crawl_huiji_res1999.py`
- Modify: `scripts/import_huiji_credentials.py`
- Modify: `scripts/refresh_huiji_credentials.py`
- Modify: `scripts/audit_credential_secrecy.py`
- Modify: `scripts/verify_huiji_project_boundary.py`
- Modify: `crawl_huiji_res1999.ps1`
- Modify: `crawl_huiji_res1999.bat`
- Create: `tests/test_huiji_crawler_tool_cli.py`
- Modify: `tests/test_huiji_cli.py`
- Modify: `tests/test_huiji_credential_import_cli.py`
- Modify: `tests/test_huiji_credential_refresh.py`
- Modify: `tests/test_huiji_start_script.py`
- Modify: `tests/test_huiji_project_boundary_script.py`

**统一命令面：**

```text
python -m src.huiji_crawler_tool crawl [crawl options]
python -m src.huiji_crawler_tool credential import --legacy-source PATH [--replace] [--output PATH]
python -m src.huiji_crawler_tool credential refresh [--transport edge|browser] [browser options]
python -m src.huiji_crawler_tool credential status [--output PATH]
python -m src.huiji_crawler_tool doctor [--output PATH]
python -m src.huiji_crawler_tool verify-package [--critical-only] [--output PATH]
```

`main()` 必须可测试注入，但生产不暴露任意 root 参数：

```python
def main(argv: Sequence[str] | None = None, *, tool_root: Path | None = None,
         environ: Mapping[str, str] | None = None) -> int: ...
```

- [ ] **Step 1: 添加统一命令和退出码 RED 测试**

```python
def test_cli_exposes_exact_p1_command_surface_without_p2_commands(): ...
def test_crawl_cli_accepts_existing_crawl_options_and_config_precedence(): ...
def test_cli_maps_every_domain_failure_to_stable_exit_code(): ...
def test_cli_error_and_json_reports_never_echo_cookie_values(): ...
def test_missing_credential_fails_before_workspace_or_network(): ...
def test_path_or_manifest_preflight_fails_before_edge_launch(): ...
def test_account_mismatch_writes_no_crawl_workspace(): ...
def test_old_scripts_only_prepend_or_translate_to_unified_cli(): ...
def test_old_import_source_alias_translates_to_legacy_source(): ...
def test_boundary_wrapper_accepts_explicit_tool_root_without_hardcoded_forbidden_root(): ...
```

- [ ] **Step 2: 运行 RED**

```powershell
& $Python -m pytest tests/test_huiji_crawler_tool_cli.py tests/test_huiji_cli.py tests/test_huiji_credential_import_cli.py tests/test_huiji_credential_refresh.py tests/test_huiji_start_script.py tests/test_huiji_project_boundary_script.py -q
```

- [ ] **Step 3: 实现一个 argparse 权威入口**

旧 Python 脚本不再 import `config.config`，不再定义独立 parser：

```python
def main(argv=None) -> int:
    return crawler_tool_main(["crawl", *(argv if argv is not None else sys.argv[1:])], tool_root=ROOT)
```

import wrapper 仅把旧 `--source` token 翻译为 `--legacy-source`；refresh wrapper 仅前置 `credential refresh`。旧 `crawl --config` 作为兼容参数只允许解析到固定 canonical credential 路径，任何其他路径退出 3，并提示使用 `config/crawler.yaml` 和固定 credential target。

`verify_huiji_project_boundary.py` 必须在解析 `--tool-root` 前只 import stdlib；随后把该工具根放到 `sys.path[0]` 并从该 root 加载统一 CLI。这样使用包内 `.venv` 运行 wrapper 时，审计 hook 覆盖的是真实解压包源码，而不是项目工作树副本。

- [ ] **Step 4: 重排 crawler 前置顺序**

`run_crawl()` 调整为：

```text
validated settings and package gate
-> acquire runtime lock
-> load canonical credential when transport=requests
-> validate local expiry
-> construct client
-> validate expected account
-> fetch siteinfo
-> only now create workspace/state/output files
-> execute dry-run or crawl
-> close client and release lock
```

`crawl`、`credential import` 和 `credential refresh` 必须持有同一个 default exclusive lock；`credential status`、`doctor` 和 `verify-package` 只读，不抢占写锁，但 doctor 要报告锁是否可用。

不得在凭据缺失、配置越界、包损坏或环境不支持时创建 `crawl_state.sqlite`、`errors.jsonl`、profile 或抓取目录。账号不匹配时不得创建抓取 workspace；browser/edge transport 可在路径与环境门禁通过后创建固定的工具内 profile，用于完成登录检查。异常写入输出时只保留 `error_type` 和脱敏消息。

- [ ] **Step 5: 更新兼容启动器**

`crawl_huiji_res1999.ps1` 移除 Conda `1999wiki` 硬依赖和自己维护的 refresh 重试流程，按以下顺序发现开发解释器：

```text
HUIJI_CRAWLER_PYTHON
py -3.12-64
python.exe on PATH
```

然后只执行 `-m src.huiji_crawler_tool crawl @Args`。BAT 保持 UTF-8 和 CRLF，仅包装 PowerShell。正式包的 `.cmd` 在 Task 6 实现。

- [ ] **Step 6: 运行 GREEN 与完整 Huiji 邻接测试**

```powershell
& $Python -m pytest tests/test_huiji_crawler_tool_cli.py tests/test_huiji_cli.py tests/test_huiji_credential_import_cli.py tests/test_huiji_credential_refresh.py tests/test_huiji_start_script.py tests/test_huiji_project_boundary_script.py tests/test_huiji_client.py tests/test_huiji_browser_client.py tests/test_huiji_read_only.py -q
& $Python -m src.huiji_crawler_tool --help
& $Python -m src.huiji_crawler_tool credential --help
```

**任务门槛：** 三个 Python wrapper 不含 `ArgumentParser`、`get_config` 或独立路径默认值；帮助输出无 `schedule`、`account add`、`dpapi` 或 GUI 命令。

---

## Task 4: Python/Edge 发现、credential status 与 doctor

**对应 specs：** `DISCOVERY-P0-01..03`、`CLI-P0-02`、`CONFIG-P0-05..07`。

**文件：**

- Create: `bootstrap/__init__.py`
- Create: `bootstrap/python_runtime.py`
- Create: `src/huiji_crawler_tool/discovery.py`
- Create: `src/huiji_crawler_tool/doctor.py`
- Modify: `src/huiji_crawler_tool/cli.py`
- Modify: `src/huijiwiki/browser_client.py`
- Modify: `config/external-path-allowlist.yaml`
- Create: `tests/test_huiji_crawler_discovery.py`
- Create: `tests/test_huiji_crawler_doctor.py`
- Modify: `tests/test_huiji_browser_client.py`

**发现顺序：**

```text
Python: HUIJI_CRAWLER_PYTHON -> py -3.12-64 -> python.exe on PATH
Edge:   --edge-executable -> HUIJI_CRAWLER_EDGE_EXECUTABLE
        -> C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
        -> C:\Program Files\Microsoft\Edge\Application\msedge.exe
```

`bootstrap/python_runtime.py` 仅依赖 stdlib，定义当前解释器校验和可序列化 `PythonRuntimeInfo`。支持条件必须同时满足：Windows、CPython、64-bit、`3.12.0 <= version < 3.13.0`。

- [ ] **Step 1: 添加 RED 测试**

```python
def test_python_runtime_accepts_only_windows_cpython_312_x64(): ...
def test_python_discovery_order_is_explicit_then_launcher_then_path(): ...
def test_edge_discovery_order_and_exact_allowlist_are_stable(): ...
def test_external_edge_does_not_relax_profile_or_output_containment(): ...
def test_doctor_is_offline_redacted_and_deterministically_sorted(): ...
def test_doctor_reports_python_dependency_edge_paths_credential_and_lock(): ...
def test_credential_status_reports_hash_names_expiry_without_values(): ...
def test_doctor_invalid_environment_returns_exit_8_without_network(): ...
```

- [ ] **Step 2: 运行 RED**

```powershell
& $Python -m pytest tests/test_huiji_crawler_discovery.py tests/test_huiji_crawler_doctor.py tests/test_huiji_browser_client.py -q
```

- [ ] **Step 3: 实现脱敏 doctor schema**

输出 schema 固定为 `huiji_crawler_doctor.v1`，至少包含：

```text
tool_root
platform / machine
current_python and discovery candidates
dependency import/version status
edge candidate source/path/status
owned path containment status
package manifest status or source_checkout status
credential present/schema/hash/size/cookie_names/expiry status
runtime lock availability
overall status
```

doctor 不访问网络，不启动 Edge，不创建 profile/workspace，不读取 Cookie value。工具根可完整显示；环境变量只记录名称、是否设置和命中来源，不记录值。

- [ ] **Step 4: 将 browser client 委托给统一 Edge discovery**

移除 `browser_client.py` 中重复的默认 Edge 常量和 Conda 安装提示。`MissingPlaywrightError` 只提示执行工具根 `install.cmd`；不得出现 `conda activate 1999wiki`。

同步把 `config/external-path-allowlist.yaml` 两个 Edge 条目的 `file` 改为 `src/huiji_crawler_tool/discovery.py`，保持精确值和类别。

- [ ] **Step 5: 运行 GREEN**

```powershell
& $Python -m pytest tests/test_huiji_crawler_discovery.py tests/test_huiji_crawler_doctor.py tests/test_huiji_browser_client.py tests/test_runtime_path_audit.py -q
& $Python -m src.huiji_crawler_tool doctor
```

Expected: 当前开发解释器通过 Python gate；doctor 可因真实凭据过期返回整体 warning，但结构和离线检查成功，且输出无 Cookie 值。

---

## Task 5: 结构化外部路径审计和越界探测

**对应 specs：** `AUDIT-P0-01..04`、`PACKAGE-P0-09`。

**文件：**

- Create: `src/huiji_crawler_tool/path_audit.py`
- Create: `bootstrap/inspect_powershell_paths.ps1`
- Create: `scripts/audit_huiji_crawler_paths.py`
- Modify: `src/runtime_path_audit.py`
- Modify: `config/external-path-allowlist.yaml`
- Create: `tests/test_huiji_crawler_path_audit.py`
- Modify: `tests/test_runtime_path_audit.py`

**解析策略：**

- `.py`：使用 `ast.parse`，收集 path-like 变量、`Path(...)` 参数和 executable/profile/config/root/out 等关键调用参数中的字符串常量。
- `.ps1`：调用 `bootstrap/inspect_powershell_paths.ps1`，使用 `[System.Management.Automation.Language.Parser]::ParseFile()`，输出 string AST 的文件、行、列和值。
- `.yaml/.yml`：使用 `yaml.safe_load` 后递归检查 path-like key 的 scalar。
- `.json`：使用 `json.loads` 后采用相同递归规则。
- `.cmd/.bat`：没有可用结构化 parser，使用明确标记为 `text_fallback` 的逐行扫描；解析失败不得静默跳过。
- `.md` 和历史 specs/plans 不作为可执行依赖扫描；HTTP(S) URL 与 loopback endpoint 不作为文件路径。
- allowlist policy 文件作为审计输入单独验证，不把其 `value` 字段再次当成生产依赖匹配。
- source 模式只扫描显式 `--include` 的 crawler 生产范围；stage 模式扫描除三个 mutable prefixes 外的完整工具包。include 路径本身必须位于 root 内且不得重叠或逃逸。

- [ ] **Step 1: 添加 RED 测试**

```python
def test_python_ast_finds_runtime_path_but_ignores_regex_and_docs(): ...
def test_powershell_parser_finds_string_paths_with_line_and_column(): ...
def test_yaml_and_json_only_classify_path_semantics(): ...
def test_cmd_fallback_is_explicit_and_parse_failure_is_not_silent(): ...
def test_audit_distinguishes_http_loopback_drive_unc_and_file_url(): ...
def test_exact_edge_allowlist_passes_and_stale_duplicate_wildcard_entries_fail(): ...
def test_symlink_and_junction_escape_are_reported_from_real_paths(): ...
def test_huiji_crawler_docs_are_non_executable_history_not_runtime_dependencies(): ...
def test_report_never_echoes_unrelated_secret_values(): ...
```

- [ ] **Step 2: 运行 RED**

```powershell
& $Python -m pytest tests/test_huiji_crawler_path_audit.py tests/test_runtime_path_audit.py -q
```

- [ ] **Step 3: 实现统一报告**

报告 schema 为 `huiji_crawler_path_audit.v1`，每个 match 记录 parser、file、line、column、value、category、allowlist_id 和 reason。完成条件必须同时满足：

```text
parse_error_count == 0
unclassified_external_path_count == 0
stale_allowlist_count == 0
duplicate_allowlist_count == 0
path_escape_count == 0
```

允许类别仍只有 `system_executable` 与 `diagnostic_sentinel`。禁止 wildcard、目录级豁免、重复 ID、重复 file/value 和未命中旧条目。

- [ ] **Step 4: 调整现有 project audit 的历史文档语义**

现有 `src/runtime_path_audit.py` 应把 `docs/huiji-crawler/specs` 和 `docs/huiji-crawler/plans` 标记为非执行历史文档，不因为文档记录旧绝对路径产生 runtime dependency 误报；生产 Python、PowerShell、YAML、JSON 和 CMD 仍由新结构化审计覆盖。

- [ ] **Step 5: 运行 GREEN 与实际源审计**

```powershell
& $Python -m pytest tests/test_huiji_crawler_path_audit.py tests/test_runtime_path_audit.py -q
& $Python scripts/audit_huiji_crawler_paths.py --root $Project --policy config/external-path-allowlist.yaml --include src/huijiwiki --include src/huiji_crawler_tool --include scripts/crawl_huiji_res1999.py --include scripts/import_huiji_credentials.py --include scripts/refresh_huiji_credentials.py --include crawl_huiji_res1999.ps1 --include crawl_huiji_res1999.bat --include config/crawler.yaml --output (Join-Path $Evidence 'path-audit-source.v1.json')
```

**任务门槛：** 实际源报告五个失败计数全部为 0；否则停止，不得用新增宽泛 allowlist 消除问题。

---

## Task 6: 实现 stdlib package verifier、安装器和 `.cmd` 启动器

**对应 specs：** `CLI-P0-01`、`PACKAGE-P0-05`、`PACKAGE-P0-07`、`DISCOVERY-P0-01..02`。

**文件：**

- Create: `bootstrap/package_verify.py`
- Create: `bootstrap/install.py`
- Create: `packaging/huiji-crawler/templates/select-python.cmd`
- Create: `packaging/huiji-crawler/templates/install.cmd`
- Create: `packaging/huiji-crawler/templates/verify-package.cmd`
- Create: `packaging/huiji-crawler/templates/huiji-crawler.cmd`
- Create: `tests/test_huiji_crawler_package_verify.py`
- Create: `tests/test_huiji_crawler_install.py`
- Create: `tests/test_huiji_crawler_cmd_launchers.py`

**package verifier 契约：**

```python
def verify_package(root: Path, *, critical_only: bool = False) -> dict[str, object]: ...
```

manifest 不自包含自身 hash。`package-manifest.v1.json` 覆盖所有不可变 payload；`package-manifest.v1.sha256` 单独固定 manifest。verifier 必须：

1. 验证 manifest sidecar。
2. 拒绝重复、绝对、`..`、大小写碰撞和越界路径。
3. 验证记录文件的 size/SHA-256。
4. full 模式拒绝 manifest 外文件，但允许 `.venv/`、`.local/`、`workspace/` 三个 mutable prefix。
5. critical 模式至少验证 launcher、bootstrap verifier、CLI、config 和依赖 lock。
6. 拒绝任何 symlink/junction 逃逸。

- [ ] **Step 1: 添加 RED 测试**

```python
def test_package_verifier_accepts_valid_manifest_and_detached_hash(): ...
def test_package_verifier_rejects_tamper_extra_duplicate_case_collision_and_parent_path(): ...
def test_package_verifier_ignores_only_exact_mutable_prefixes(): ...
def test_package_verifier_rejects_symlink_or_junction_escape(): ...
def test_install_rejects_non_windows_non_cpython_non_312_or_32_bit(): ...
def test_install_uses_require_hashes_only_binary_and_tool_local_venv(): ...
def test_install_failure_leaves_no_success_marker(): ...
def test_cmd_launchers_quote_space_and_unicode_roots_and_forward_all_args(): ...
def test_runtime_launcher_verifies_critical_files_before_cli_import(): ...
def test_cmd_files_use_crlf_and_contain_no_conda_or_absolute_project_path(): ...
```

- [ ] **Step 2: 运行 RED**

```powershell
& $Python -m pytest tests/test_huiji_crawler_package_verify.py tests/test_huiji_crawler_install.py tests/test_huiji_crawler_cmd_launchers.py -q
```

- [ ] **Step 3: 实现安装流程**

构建时把 `select-python.cmd` 映射到包内 `bootstrap/select-python.cmd`。它的候选顺序固定为 `HUIJI_CRAWLER_PYTHON`、`py -3.12-64`、PATH `python.exe`。`install.cmd` 调用 stdlib `bootstrap/install.py`，后者：

```text
validate current interpreter
-> verify critical package files
-> create <root>/.venv with venv
-> <venv-python> -m pip install --require-hashes --only-binary=:all: -r requirements-crawler.lock.txt
-> import requests, yaml, playwright
-> run python -m src.huiji_crawler_tool --help
-> atomically write .venv/.huiji-crawler-install.v1.json
```

success marker 记录 Python version、machine、lock SHA-256 和 manifest SHA-256，不含安装机用户名或绝对源项目路径。任一命令失败删除临时 marker，不声称成功。

- [ ] **Step 4: 实现运行启动器**

`huiji-crawler.cmd` 只使用 `<root>\.venv\Scripts\python.exe`。若缺失或 marker 不匹配，退出 8 并提示运行 `install.cmd`；存在时先运行 `bootstrap\package_verify.py --critical-only`，成功后才执行：

```text
<venv-python> -m src.huiji_crawler_tool %*
```

`verify-package.cmd` 可在安装前通过 system Python 执行 full verifier。所有 `.cmd` 使用 `%~dp0` 定位真实根、正确引用带空格/中文路径，并保存 CRLF。

- [ ] **Step 5: 运行 GREEN**

```powershell
& $Python -m pytest tests/test_huiji_crawler_package_verify.py tests/test_huiji_crawler_install.py tests/test_huiji_crawler_cmd_launchers.py -q
& $Python -m compileall -q bootstrap
```

---

## Task 7: 锁定依赖并实现 crawler-only 确定性构建

**对应 specs：** `PACKAGE-P0-01..10`、`AUDIT-P0-01..04`。

**文件：**

- Create: `src/huiji_crawler_packaging/__init__.py`
- Create: `src/huiji_crawler_packaging/dependency_lock.py`
- Create: `src/huiji_crawler_packaging/standard_package.py`
- Create: `scripts/lock_huiji_crawler_requirements.py`
- Create: `scripts/build_huiji_crawler_standard_package.py`
- Create: `packaging/huiji-crawler/files.v1.yaml`
- Create: `packaging/huiji-crawler/requirements-crawler.in`
- Create: `packaging/huiji-crawler/requirements-crawler.lock.txt`
- Create: `packaging/huiji-crawler/size-policy.v1.json`
- Create: `packaging/huiji-crawler/README.md`
- Create: `packaging/huiji-crawler/templates/README.md`
- Create: `tests/test_huiji_crawler_dependency_lock.py`
- Create: `tests/test_huiji_crawler_package_builder.py`

### 7.1 直接依赖输入

`packaging/huiji-crawler/requirements-crawler.in` 精确为：

```text
playwright==1.61.0
PyYAML==6.0.3
requests==2.34.2
```

lock 生成器必须调用 pip resolver 下载 CPython 3.12/win_amd64 的 binary wheels，再从 wheel filename/METADATA 生成排序后的完整 `name==version --hash=sha256:<wheel-hash>`。不得从当前 Conda `pip freeze` 复制无关包。

```powershell
& $Python scripts/lock_huiji_crawler_requirements.py --input packaging/huiji-crawler/requirements-crawler.in --output packaging/huiji-crawler/requirements-crawler.lock.txt --wheelhouse dist/huiji-crawler/wheel-cache --python-version 3.12 --platform win_amd64
```

### 7.2 精确 allowlist

`files.v1.yaml` 只允许以下静态输入及目录内明确列出的文件：

```text
bootstrap/__init__.py
bootstrap/install.py
bootstrap/package_verify.py
bootstrap/python_runtime.py
bootstrap/inspect_powershell_paths.ps1
config/crawler.yaml
config/external-path-allowlist.yaml
src/__init__.py
src/huijiwiki/__init__.py
src/huijiwiki/browser_client.py
src/huijiwiki/client.py
src/huijiwiki/cookies.py
src/huijiwiki/crawler.py
src/huijiwiki/credential_refresh.py
src/huijiwiki/credential_schema.py
src/huijiwiki/credential_store.py
src/huijiwiki/enumerator.py
src/huijiwiki/errors.py
src/huijiwiki/jsonl.py
src/huijiwiki/legacy_credentials.py
src/huijiwiki/models.py
src/huijiwiki/progress.py
src/huijiwiki/project_paths.py
src/huijiwiki/resources.py
src/huijiwiki/revisions.py
src/huijiwiki/state.py
src/huiji_crawler_tool/__init__.py
src/huiji_crawler_tool/__main__.py
src/huiji_crawler_tool/cli.py
src/huiji_crawler_tool/config.py
src/huiji_crawler_tool/discovery.py
src/huiji_crawler_tool/doctor.py
src/huiji_crawler_tool/errors.py
src/huiji_crawler_tool/path_audit.py
src/huiji_crawler_tool/runtime_lock.py
src/huiji_crawler_tool/runtime_paths.py
```

构建器把 packaging 模板映射为包根的 `huiji-crawler.cmd`、`install.cmd`、`verify-package.cmd`、`README.md`，并把 `select-python.cmd` 映射为 `bootstrap/select-python.cmd`，把两份 requirements 映射到包根。`src/huijiwiki/integrity.py`、`resource_downloader.py`、所有其他 `src/**`、`scripts/**`、`docs/**` 和完整项目配置默认不进入包。

无条件 forbidden prefixes/names：

```text
.env
.git/
.idea/
.local/
.venv/
data/
dist/
eval/
infra/
node_modules/
tests/
vectorstore/
workspace/
__pycache__/
*.pyc
```

- [ ] **Step 1: 添加 RED 测试**

```python
def test_lock_contains_only_complete_win_amd64_cp312_binary_graph_with_hashes(): ...
def test_lock_generation_is_sorted_and_reproducible(): ...
def test_allowlist_rejects_globs_unknown_roles_duplicate_destinations_and_missing_inputs(): ...
def test_staging_contains_only_explicit_crawler_runtime_files(): ...
def test_staging_unconditionally_excludes_data_secrets_rag_backend_frontend_and_profiles(): ...
def test_secret_scan_uses_private_cookie_values_without_serializing_them(): ...
def test_manifest_covers_every_immutable_payload_with_role_size_and_sha256(): ...
def test_manifest_sidecar_and_package_verifier_agree(): ...
def test_sbom_is_valid_cyclonedx_and_matches_locked_components(): ...
def test_third_party_notices_and_license_files_match_wheel_metadata(): ...
def test_build_receipt_contains_no_wall_clock_or_machine_specific_absolute_path(): ...
def test_zip_order_timestamp_permissions_and_hash_are_deterministic(): ...
def test_size_target_warns_and_only_zip_over_50_mib_blocks(): ...
def test_build_failure_publishes_no_release_zip(): ...
```

- [ ] **Step 2: 运行 RED**

```powershell
& $Python -m pytest tests/test_huiji_crawler_dependency_lock.py tests/test_huiji_crawler_package_builder.py -q
```

- [ ] **Step 3: 实现 staged build DAG**

构建顺序固定为：

```text
validate allowlist and lock
-> copy allowlisted static inputs into new staging
-> materialize launcher/README/requirements destinations
-> run structured path audit
-> run filename/scope and credential-value secret audit
-> generate CycloneDX SBOM and license materials from verified wheels
-> generate deterministic build receipt and uncompressed size report
-> generate package-manifest over all immutable payload except manifest/sidecar
-> generate detached manifest SHA-256
-> full verify staging
-> create sorted fixed-timestamp ZIP in temporary output
-> reopen ZIP and full verify extracted logical tree
-> enforce 50 MiB gross hard cap
-> atomically publish ZIP, ZIP SHA-256 and external size report
```

`SOURCE_DATE_EPOCH` 固定为 `1784505600`（2026-07-20 00:00:00 UTC）；ZIP entry timestamp、文件顺序和权限全部由构建器设置。build receipt 只记录 schema、source epoch、allowlist/lock/policy hash、source tree hash 和构建工具版本。

SBOM 的 metadata timestamp 同样来自 `SOURCE_DATE_EPOCH`；serial number 使用由 source tree hash 派生的 UUIDv5，禁止随机 UUID 或当前时间破坏双构建一致性。

`package-manifest.v1.json` schema 必须包含 target、mutable prefixes，以及每个文件的 path、role、critical、size、SHA-256。以下示例使用合法的 64 位十六进制测试值说明字段形状，构建时必须替换为真实值：

```json
{
  "schema_version": "huiji_crawler_package_manifest.v1",
  "target": {"os": "windows", "arch": "x64", "python": ">=3.12.0,<3.13"},
  "mutable_prefixes": [".local/", ".venv/", "workspace/"],
  "files": [
    {"path": "src/huiji_crawler_tool/cli.py", "role": "runtime_source", "critical": true, "size": 1, "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}
  ]
}
```

- [ ] **Step 4: 实现 secret 与误打包阻断**

若 `.local/accounts/default/credential.json` 存在，构建器只在内存中读取 sensitive Cookie 值用于 staging 搜索；报告只列命中的目标文件与 Cookie 名。即使凭据不存在，也必须执行 forbidden filename/prefix、典型 Cookie/header 结构和高风险配置字段扫描。

任何失败只保留 staging/evidence 供诊断，不把临时 ZIP rename 为正式产物。

- [ ] **Step 5: 运行 GREEN**

```powershell
& $Python -m pytest tests/test_huiji_crawler_dependency_lock.py tests/test_huiji_crawler_package_builder.py tests/test_huiji_crawler_package_verify.py tests/test_huiji_crawler_path_audit.py -q
& $Python -m compileall -q src/huiji_crawler_packaging scripts/lock_huiji_crawler_requirements.py scripts/build_huiji_crawler_standard_package.py
```

---

## Task 8: 构建标准 ZIP 并执行确定性与内容门禁

**对应 specs：** `PACKAGE-P0-01..10`、`AUDIT-P0-01..04`。

**输入：** Task 7 的 allowlist、lock、wheel cache 和构建器。  
**输出：** `dist/huiji-crawler/p1-a/**`、`dist/huiji-crawler/p1-b/**`、`eval/huiji-crawler/<run-id>/p1/package/**`。

- [ ] **Step 1: 生成或验证完整 hash lock**

```powershell
& $Python scripts/lock_huiji_crawler_requirements.py --input packaging/huiji-crawler/requirements-crawler.in --output packaging/huiji-crawler/requirements-crawler.lock.txt --wheelhouse dist/huiji-crawler/wheel-cache --python-version 3.12 --platform win_amd64
& $Python -m pytest tests/test_huiji_crawler_dependency_lock.py -q
```

网络、wheel、metadata 或 hash 任一失败即停止。标准 ZIP 不包含 `wheel-cache`。

- [ ] **Step 2: 从同一输入独立构建两次**

```powershell
& $Python scripts/build_huiji_crawler_standard_package.py --project-root $Project --policy packaging/huiji-crawler/files.v1.yaml --lock packaging/huiji-crawler/requirements-crawler.lock.txt --wheelhouse dist/huiji-crawler/wheel-cache --output dist/huiji-crawler/p1-a --evidence (Join-Path $Evidence 'package/build-a')
& $Python scripts/build_huiji_crawler_standard_package.py --project-root $Project --policy packaging/huiji-crawler/files.v1.yaml --lock packaging/huiji-crawler/requirements-crawler.lock.txt --wheelhouse dist/huiji-crawler/wheel-cache --output dist/huiji-crawler/p1-b --evidence (Join-Path $Evidence 'package/build-b')
```

- [ ] **Step 3: 比较双构建**

```powershell
$ZipA = Join-Path $Project 'dist\huiji-crawler\p1-a\huiji-crawler-windows-standard.zip'
$ZipB = Join-Path $Project 'dist\huiji-crawler\p1-b\huiji-crawler-windows-standard.zip'
$HashA = (Get-FileHash -LiteralPath $ZipA -Algorithm SHA256).Hash
$HashB = (Get-FileHash -LiteralPath $ZipB -Algorithm SHA256).Hash
if ($HashA -ne $HashB) { throw "Deterministic ZIP hash mismatch: $HashA != $HashB" }
```

同时比较两次 build receipt、manifest、SBOM 和 stage tree hash。任一不同都视为确定性失败。

- [ ] **Step 4: 解压后执行 full package verification 和内容清点**

```powershell
$VerifyRoot = Join-Path $Evidence 'package\verified-extract'
if (Test-Path -LiteralPath $VerifyRoot) { throw "Verification root already exists" }
Expand-Archive -LiteralPath $ZipA -DestinationPath $VerifyRoot
$env:HUIJI_CRAWLER_PYTHON = $Python
& (Join-Path $VerifyRoot 'verify-package.cmd')
if ($LASTEXITCODE -ne 0) { throw "Package verification failed" }
```

再断言以下内容计数为 0：Cookie/`.env`/profile/抓取数据、RAG、backend、frontend、Docker/数据库、allowlist 外源码、绝对原项目路径。确认 ZIP 不含 wheel、Python runtime 或 `.venv`。

- [ ] **Step 5: 记录体积与发布候选**

标准 ZIP 超过参考目标只写 warning；只有 ZIP 大于 50 MiB 或出现明显误打包内容才阻断。通过后把 `p1-a` 标记为 relocation candidate，不删除 `p1-b`，以便复审确定性证据。

---

## Task 9: 四路径搬迁、真实 Edge/Requests 验收与最终收口

**对应 specs：** 全部 36 个 P0 条目与规格第 9.2、9.3 节。

**修改文档：**

- Modify: `docs/huiji-crawler/README.md`
- Modify: `docs/huiji-crawler/plans/README.md`
- Modify after acceptance: `docs/huiji-crawler/specs/2026-07-20-windows-crawler-p1-portable-tool-design.md`
- Modify after acceptance: 本计划状态与完成清单

### 9.1 四个 relocation root

```text
D:\Temp\huiji-crawler-p1-plain
D:\Temp\huiji crawler p1 space
D:\Temp\灰机爬虫 P1
C:\Temp\huiji-crawler-p1-cross-drive
```

每个目标必须在开始时不存在；若已存在，使用新的带 run-id 目录，禁止覆盖或清理未知内容。每个 root 独立解压同一个 `ZipA`。

- [x] **Step 1: 每个 root 执行无凭据 fail-closed 验收**

按顺序执行：

```text
verify-package.cmd                          -> 0
install.cmd                                 -> 0
huiji-crawler.cmd verify-package            -> 0
huiji-crawler.cmd doctor                    -> 0 或仅 credential warning
huiji-crawler.cmd credential status         -> 2（凭据尚不存在）
huiji-crawler.cmd crawl --dry-run            -> 2（凭据尚不存在）
```

最后两条必须确认：没有启动 Edge、没有网络请求、没有创建 `workspace/default/res1999`。四个 root 的 `.venv`、`.local` 和后续 workspace 都必须位于各自 root 内。

- [x] **Step 2: 对四个 root 执行 package/path 审计**

每个 root 的 full package verification、结构化路径审计和真实路径 containment 均通过；除两个精确 Edge executable 外，没有外部文件依赖。检查所有报告中不存在 `D:\PycharmProjects\nlp\LangChain\1999Search` 或 `D:\1999WIKI_ROBOT` 作为运行依赖。

- [x] **Step 3: 在中文路径 root 完成一次真实 Edge refresh**

使用 `D:\Temp\灰机爬虫 P1`：

```powershell
$RealRoot = 'D:\Temp\灰机爬虫 P1'
& (Join-Path $RealRoot 'huiji-crawler.cmd') credential refresh --transport edge --expected-user 'POTATO BOT'
if ($LASTEXITCODE -ne 0) { throw "Real Edge refresh failed" }
& (Join-Path $RealRoot 'huiji-crawler.cmd') credential status --output '.local/accounts/default/credential-status.v1.json'
if ($LASTEXITCODE -ne 0) { throw "Credential status failed after refresh" }
```

允许用户在系统 Edge 中完成登录/Cloudflare 验证。refresh 成功后必须生成 strict `huiji_credential.v2`，目标只在该工具 root 内，报告无 Cookie 值。

- [x] **Step 4: 使用真实 Requests 执行只读 dry-run**

```powershell
$PackagePython = Join-Path $RealRoot '.venv\Scripts\python.exe'
& $PackagePython (Join-Path $Project 'scripts\verify_huiji_project_boundary.py') --tool-root $RealRoot --forbid-root 'D:\1999WIKI_ROBOT' --evidence (Join-Path $Evidence 'real\forbidden-root-requests.v1.json') -- crawl --transport requests --dry-run
if ($LASTEXITCODE -ne 0) { throw "Real Requests dry-run or boundary guard failed" }
```

验收必须得到：

```text
blocked_access_count == 0
crawler_exit_code == 0
account == POTATO BOT
siteinfo.json exists
crawl_state.sqlite exists only below RealRoot/workspace/default/res1999
no non-read-only API action
```

- [x] **Step 5: 对旧凭据源做前后 hash 对照**

若 Task 0 记录了 `.local/huiji/credentials/config.dat`，重新记录 size、mtime、SHA-256，并与 baseline 做精确比较。任何变化立即停止验收并调查；不得删除旧源。

- [x] **Step 6: 执行 package secret、可再生数据和边界复检**

真实 refresh 后重新验证原 ZIP 和 source staging 不包含新凭据值。构建器 secret audit 可以读取 `RealRoot/.local/accounts/default/credential.json` 作为仅内存扫描输入，但输出只能记录 violation count 和 Cookie 名称。原 ZIP hash 必须保持不变。

- [ ] **Step 7: 运行最终自动化回归**

```powershell
& $Python -m pytest tests/test_huiji_crawler_tool_paths.py tests/test_huiji_crawler_tool_config.py tests/test_huiji_crawler_runtime_lock.py tests/test_huiji_credential_schema.py tests/test_huiji_legacy_credentials.py tests/test_huiji_crawler_tool_cli.py tests/test_huiji_crawler_discovery.py tests/test_huiji_crawler_doctor.py tests/test_huiji_crawler_path_audit.py tests/test_huiji_crawler_package_verify.py tests/test_huiji_crawler_install.py tests/test_huiji_crawler_cmd_launchers.py tests/test_huiji_crawler_dependency_lock.py tests/test_huiji_crawler_package_builder.py -q
& $Python -m pytest -q
& $Python -m compileall -q src bootstrap scripts
```

- [ ] **Step 8: 生成最终验收 receipt**

最终 `eval/huiji-crawler/<run-id>/p1/final-acceptance.v1.json` 必须 hash-pin：

```text
spec and plan
full pytest result
two deterministic build receipts
ZIP SHA-256
package manifest and detached hash
SBOM and license inventory
source/staging/four-root path audits
four-root command results
real Edge refresh redacted report
real Requests forbidden-root report
old credential source before/after evidence
secret scan and size report
```

只有所有 hard gate 为 passed 才把规格和计划状态改为“P1 已完成并通过验收”。若真实登录因外部站点或用户交互无法完成，状态保持“实现完成，真实 transport 验收未完成”，不得宣称 P1 完成。

---

## 6. 完成后逐项自检

### CLI

- [ ] `CLI-P0-01`：包内 `huiji-crawler.cmd` 从真实脚本路径定位 root，四个 relocation root 均通过。
- [ ] `CLI-P0-02`：六个 P1 命令存在且可执行，无 P2 命令。
- [ ] `CLI-P0-03`：三个旧 Python 入口只委托统一 CLI。
- [ ] `CLI-P0-04`：无 GUI、托盘或常驻进程。
- [ ] `CLI-P0-05`：退出码稳定，错误提供工具内恢复命令且无秘密。

### Config

- [ ] `CONFIG-P0-01`：crawler 只读 `config/crawler.yaml`，入口不 import RAG settings。
- [ ] `CONFIG-P0-02`：CLI、env、YAML、defaults 优先级测试通过。
- [ ] `CONFIG-P0-03`：全部 owned paths 在工具 root 内。
- [ ] `CONFIG-P0-04`：绝对路径、`..`、symlink、junction 逃逸均前置停止。
- [ ] `CONFIG-P0-05`：只有精确 Edge executable 可在 root 外。
- [ ] `CONFIG-P0-06`：默认输出为 `workspace/default/res1999` 且不在 ZIP。
- [ ] `CONFIG-P0-07`：配置、doctor 和错误报告不含凭据值。

### Credential

- [ ] `CREDENTIAL-P0-01`：稳定 loader 只接受 `huiji_credential.v2`。
- [ ] `CREDENTIAL-P0-02`：legacy decoder 只由显式 import 命令调用。
- [ ] `CREDENTIAL-P0-03`：目标固定在 `.local/accounts/default/credential.json`，源可外部且不被修改。
- [ ] `CREDENTIAL-P0-04`：结构/hash/size/names 验证、冲突停止和 replace 通过。
- [ ] `CREDENTIAL-P0-05`：真实 Edge refresh 直接写 v2。
- [ ] `CREDENTIAL-P0-06`：凭据不在 Git、包、日志、evidence 或快照。
- [ ] `CREDENTIAL-P0-07`：flush/fsync/re-read/atomic replace 和失败保持原目标测试通过。

### Package

- [ ] `PACKAGE-P0-01`：`files.v1.yaml` 是唯一 source allowlist，新文件默认不入包。
- [ ] `PACKAGE-P0-02`：包只含允许的 crawler runtime、配置、启动器、lock、manifest、SBOM、license、README。
- [ ] `PACKAGE-P0-03`：所有禁止目录/文件计数为 0。
- [ ] `PACKAGE-P0-04`：direct input 与完整 hash lock 已生成和验证。
- [ ] `PACKAGE-P0-05`：install 校验 Python、创建 root-local `.venv`、`--require-hashes` 安装并 smoke 成功。
- [ ] `PACKAGE-P0-06`：双构建 ZIP/tree hash 完全一致。
- [ ] `PACKAGE-P0-07`：manifest 覆盖全部 immutable payload，detached hash 正确。
- [ ] `PACKAGE-P0-08`：SBOM、license、receipt、ZIP SHA-256、size report 齐全。
- [ ] `PACKAGE-P0-09`：secret、绝对原项目路径和 allowlist 外文件均为 0。
- [ ] `PACKAGE-P0-10`：体积 warning 不误阻断，50 MiB gross cap 和明显误打包会阻断。

### Discovery And Audit

- [ ] `DISCOVERY-P0-01`：只接受 Windows x64 CPython 3.12。
- [ ] `DISCOVERY-P0-02`：Python 顺序、版本和命中路径进入脱敏 doctor。
- [ ] `DISCOVERY-P0-03`：Edge 发现顺序正确，profile/output containment 未放宽。
- [ ] `AUDIT-P0-01`：Python/PowerShell/YAML/JSON 使用对应结构化解析器，CMD fallback 明确。
- [ ] `AUDIT-P0-02`：drive、UNC、file URL、symlink、junction 生产入口测试通过。
- [ ] `AUDIT-P0-03`：HTTP(S)、loopback 和非执行历史文档无误报。
- [ ] `AUDIT-P0-04`：allowlist 仅有精确 Edge/system sentinel，无宽泛、重复或 stale 条目。

## 7. 最终停止条件

遇到下列情况立即停止当前任务，保存证据并调查，不自动放宽门禁：

- 旧凭据源 hash、size 或 mtime 发生非预期变化。
- 任一 package manifest/hash、双构建 hash 或 lock hash 不一致。
- staging/ZIP 出现秘密、抓取数据、RAG/后端/前端、数据库或外部项目路径。
- 结构化审计出现 parse error、unclassified、stale、duplicate 或 path escape。
- 真实 Requests 验收访问 `D:\1999WIKI_ROBOT`，或产生非只读 API action。
- 完整测试出现本任务引入的回归。

Cloudflare 临时 challenge、网络瞬断或 Edge 登录等待不直接判定设计失败；允许在同一隔离 root 内重试。只有无法在不降低安全/完整性契约的前提下继续时才请求人工决策。
