# Project-Local Runtime Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将灰机爬虫的凭据、状态和项目数据路径完全收束到 `1999Search`，提供不依赖旧 GUI 的凭据导入与刷新能力，并用自动审计阻止外部项目路径重新进入正式运行链路。

**Architecture:** 中央配置加载项目根 `.env` 和 `settings.yaml`，统一的 path guard 将凭据、爬虫输出和浏览器 profile 约束在解析后的项目根内。Requests transport 从项目内结构化凭据加载 Cookie，Browser/Edge transport 负责交互式认证和项目内凭据刷新；一次性导入器是唯一可显式读取项目外凭据源的组件。路径审计器扫描生产运行范围并通过窄 allowlist 分类系统程序路径和诊断哨兵。

**Tech Stack:** Python 3.11、pytest、PyYAML、python-dotenv、Playwright、PowerShell、canonical JSON、Windows filesystem audit hook。

**Spec:** `docs/superpowers/specs/2026-07-19-project-local-runtime-boundaries-design.md`

## Global Constraints

- 本计划主线只实现 Spec 的 P0；P1/P2 只记录在 Deferred，不得顺手实施。
- 真实 `.env`、`.local/**`、Cookie 值和完整 Cookie header 不得进入 Git、文档、日志、测试快照或审计 JSON。
- `config/settings.yaml` 和 `.env.example` 只能包含空值或项目相对路径示例。
- 项目自有数据、配置、凭据、状态和输出必须位于解析后的 `1999Search` 根目录内；系统浏览器可执行文件和 HTTP(S) 服务端点按外部系统依赖分类。
- 一次性凭据导入器可读取用户显式指定的外部源文件，但不得硬编码旧目录，且目标必须是项目内解析后的凭据路径。
- 不删除、不移动、不覆盖 `D:\1999WIKI_ROBOT` 中的原文件；隔离验收使用进程内文件访问门禁。
- 保持 Huiji crawler-only provenance、只读 crawler action、Milvus、MinIO、MySQL 和 RAG 行为不变。
- 工作区包含其他任务的未提交改动；只修改本计划列出的文件，不执行 Git 提交、暂存、回滚或清理。
- 执行测试前用当前环境发现解释器，不把本机 Python 绝对路径写入源码或活动文档：

```powershell
$Py = (conda run -n langchain python -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
if (-not (Test-Path -LiteralPath $Py)) { throw "langchain Python not found" }
```

---

## 1. 目标范围

本计划必须完成：

- `CRED-P0-01` 至 `CRED-P0-07`
- `MIG-P0-01` 至 `MIG-P0-04`
- `REFRESH-P0-01` 至 `REFRESH-P0-04`
- `BOUND-P0-01` 至 `BOUND-P0-06`
- `AUDIT-P0-01` 至 `AUDIT-P0-07`

本计划不执行：旧 Obsidian 代码删除、pickle 格式淘汰、私有部署包构建、系统密钥环、自动轮换、容器化 crawler 或 Linux 跨平台验收。

## 2. 强制验收门槛

- [ ] 配置优先级固定为 `--config > HUIJI_CONFIG_PATH > settings.yaml > .local/huiji/credentials/config.dat`。
- [ ] 凭据、out、Browser profile 和 Edge profile 的外部绝对路径、`..` 穿越和 symlink/junction 逃逸均在访问前失败。
- [ ] Requests 缺少或损坏凭据时脱敏失败；Browser/Edge 不读取 Requests 凭据。
- [ ] 一次性导入前后 size、SHA-256 和 Cookie 名称集合一致；不同内容默认停止，显式 replace 才能原子替换。
- [ ] Browser/Edge 只有在 `expected_user` 验证通过且 Huiji Cookie 集非空时才原子刷新项目内凭据。
- [ ] 生产运行范围中 `robot_root`、旧 Robot 路径和外部 Obsidian vault 路径零命中。
- [ ] 路径审计 `unclassified_external_path_count == 0`，allowlist 无宽泛或陈旧条目。
- [ ] 真实 Requests dry-run、Browser/Edge 账号验证、真实凭据迁移和完整 inventory 均有脱敏证据。
- [ ] 隔离验收阻断对旧目录的任何 Python 文件访问，且不移动、删除或改写旧目录。
- [ ] targeted tests、完整 Python tests 和文档/秘密机械检查全部通过。

---

### Task 1: Project-root path guard and central configuration

**Specs:** CRED-P0-01, CRED-P0-02, CRED-P0-03, CRED-P0-05, BOUND-P0-03, BOUND-P0-04

**Files:**
- Create: `src/huijiwiki/project_paths.py`
- Modify: `config/config.py`
- Modify: `config/settings.yaml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `tests/test_huiji_project_paths.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `ProjectPathViolation(ValueError)`.
- Produces: `resolve_project_local_path(value: str | Path, *, project_root: Path, label: str, must_exist: bool = False) -> Path`.
- Produces: `HuijiCfg.credential_file: Path`.
- Consumes later: Tasks 2-6 use the same resolver; no task may add an alternative string-prefix path check.

- [ ] **Step 1: Write failing containment tests**

Add tests covering relative success, absolute-inside success, external drive rejection, `..` rejection and an available symlink/junction escape. The assertions must use resolved paths:

```python
def test_resolve_project_local_path_rejects_external_absolute_path(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(ProjectPathViolation, match="credential_file"):
        resolve_project_local_path(
            tmp_path / "outside" / "config.dat",
            project_root=root,
            label="credential_file",
        )


def test_resolve_project_local_path_accepts_project_relative_path(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    resolved = resolve_project_local_path(
        ".local/huiji/credentials/config.dat",
        project_root=root,
        label="credential_file",
    )
    assert resolved == (root / ".local/huiji/credentials/config.dat").resolve()
```

- [ ] **Step 2: Write failing config priority tests**

Extend `tests/test_config.py` to reset `_config`, isolate environment variables and assert:

```python
def test_huiji_credential_file_defaults_inside_project(monkeypatch):
    monkeypatch.delenv("HUIJI_CONFIG_PATH", raising=False)
    reset_config_for_test()
    cfg = get_config()
    assert cfg.huiji.credential_file == (
        cfg.paths.project_root / ".local/huiji/credentials/config.dat"
    ).resolve()


def test_huiji_credential_env_override_cannot_escape_project(monkeypatch, tmp_path):
    monkeypatch.setenv("HUIJI_CONFIG_PATH", str(tmp_path / "outside.dat"))
    reset_config_for_test()
    with pytest.raises(ProjectPathViolation, match="HUIJI_CONFIG_PATH"):
        get_config()
```

Also change `ObsidianCfg.vault_path` from `str` to `Path`, then assert `cfg.obsidian.vault_path == cfg.paths.project_root / "data/legacy/obsidian"` and that it remains inside the project.

Add parameterized config tests proving `huiji.raw_root`, `huiji.processed_root` and `huiji.provenance_baseline` reject external absolute values and `..` escapes. These tests must monkeypatch the parsed YAML input rather than modifying the real settings file.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
& $Py -m pytest tests/test_huiji_project_paths.py tests/test_config.py -q
```

Expected: collection/import failure for `project_paths` or missing `HuijiCfg.credential_file`.

- [ ] **Step 4: Implement the single containment primitive**

Implement `src/huijiwiki/project_paths.py` with this contract:

```python
class ProjectPathViolation(ValueError):
    pass


def resolve_project_local_path(
    value: str | Path,
    *,
    project_root: Path,
    label: str,
    must_exist: bool = False,
) -> Path:
    root = project_root.expanduser().resolve(strict=True)
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectPathViolation(
            f"{label} must resolve inside the project root: {resolved}"
        ) from exc
    return resolved
```

Do not add path-prefix string comparisons. If the Windows test environment cannot create symlinks, skip only that test with the OS error reason; the non-symlink escape tests remain mandatory.

- [ ] **Step 5: Wire central configuration and private-file defaults**

Modify `HuijiCfg` to include `credential_file: Path`; load it from:

```python
credential_value = (
    os.environ.get("HUIJI_CONFIG_PATH")
    or huiji_raw.get("credential_file")
    or ".local/huiji/credentials/config.dat"
)
credential_file = resolve_project_local_path(
    credential_value,
    project_root=project_root,
    label=("HUIJI_CONFIG_PATH" if os.environ.get("HUIJI_CONFIG_PATH") else "huiji.credential_file"),
)
```

Resolve the disabled Obsidian compatibility path plus `huiji.raw_root`, `huiji.processed_root` and `huiji.provenance_baseline` through the same guard. Update active settings to:

```yaml
obsidian:
  vault_path: "data/legacy/obsidian"
huiji:
  credential_file: ".local/huiji/credentials/config.dat"
```

Add `HUIJI_CONFIG_PATH=.local/huiji/credentials/config.dat` to `.env.example`, and add `.local/` to `.gitignore`.

- [ ] **Step 6: Run focused tests and config smoke**

Run:

```powershell
& $Py -m pytest tests/test_huiji_project_paths.py tests/test_config.py -q
& $Py -c "from config.config import get_config; c=get_config(); print(c.huiji.credential_file.relative_to(c.paths.project_root))"
git check-ignore .env .local/huiji/credentials/config.dat
```

Expected: tests pass; smoke prints `.local\huiji\credentials\config.dat` or POSIX-equivalent; both private paths are ignored.

---

### Task 2: Remove robot-root runtime coupling and enforce crawler paths

**Specs:** CRED-P0-04, CRED-P0-06, CRED-P0-07, BOUND-P0-01, BOUND-P0-02, BOUND-P0-03, REFRESH-P0-04

**Files:**
- Modify: `src/huijiwiki/cookies.py`
- Modify: `src/huijiwiki/crawler.py`
- Modify: `src/huijiwiki/errors.py`
- Modify: `scripts/crawl_huiji_res1999.py`
- Modify: `crawl_huiji_res1999.ps1`
- Modify: `tests/test_huiji_cookies.py`
- Modify: `tests/test_huiji_cli.py`
- Modify: `tests/test_huiji_start_script.py`

**Interfaces:**
- `CookieLoader(config_path: str | Path)` replaces the robot-root constructor.
- `CredentialLoadError(HuijiCrawlerError)` provides a redacted Requests failure.
- `CrawlConfig.project_root: Path` and `CrawlConfig.config_path: Path` are required; `CrawlConfig.robot_root` is removed.
- `CrawlConfig.__post_init__()` validates `config_path`, `out`, `browser_profile` and `edge_profile`, but not the external system `edge_executable`.
- Task 3 consumes the same `CookieLoader`; Task 4 consumes validated profile/target paths.

- [ ] **Step 1: Rewrite cookie-loader tests to the explicit-file contract**

Replace robot directory fixtures with direct files:

```python
loader = CookieLoader(config_path)
cookies = loader.load_cookies()
assert cookies["huiji_session"] == "session-value"
assert "session-value" not in loader.describe()
```

Delete the unused `.env` credentials test and add failure tests for missing and malformed files. Keep JSON, line format, pickled GUI format and `__cf_bm` expiry coverage.

- [ ] **Step 2: Add failing crawler interface and transport-isolation tests**

Update every `CrawlConfig(...)` in `tests/test_huiji_cli.py` to pass `project_root=tmp_path`, `config_path=tmp_path / "config.dat"` and remove `robot_root`. CLI tests must call a testable builder/main entry with `project_root=tmp_path`, so temporary paths model a relocated project rather than bypassing containment. Add assertions that:

```python
assert "robot_root" not in CrawlConfig.__dataclass_fields__
assert "--robot-root" not in build_parser().format_help()
```

Monkeypatch `CookieLoader.load_cookies` to raise for Browser/Edge tests and prove those transports never call it. Add CLI tests proving external `--config`, `--out`, `--browser-profile` and `--edge-profile` fail before `run_crawl`, while an external `--edge-executable` remains permitted as a system dependency.

- [ ] **Step 3: Add failing redaction and refresh-guidance tests**

Use a sentinel Cookie value and assert it is absent from `CookieLoader.describe()`, `CrawlConfig.to_json()`, stderr and stdout. Update expiry expectations from old GUI text to the project-local command:

```text
python scripts/refresh_huiji_credentials.py --transport edge
```

- [ ] **Step 4: Run focused tests and verify RED**

Run:

```powershell
& $Py -m pytest tests/test_huiji_cookies.py tests/test_huiji_cli.py tests/test_huiji_start_script.py -q
```

Expected: failures reference the old constructor, `robot_root`, external path acceptance or GUI refresh wording.

- [ ] **Step 5: Refactor CookieLoader and CrawlConfig**

Change the loader constructor to:

```python
class CookieLoader:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self._cookie_names: list[str] = []
        self._cookie_expires: dict[str, int | None] = {}
```

Remove `load_credentials`, `env_path`, `robot_root` and the `dotenv_values` import. In `CrawlConfig`, remove `robot_root`, make `project_root` and `config_path` required fields beside `out`, validate all crawler-owned paths in `__post_init__`, and omit secret content from `to_json()`.

`load_default_cookies` must be exactly based on `config.config_path`. Wrap `FileNotFoundError`, `OSError`, parse errors and empty Cookie results as `CredentialLoadError`; the CLI returns a nonzero exit code and prints only the project-relative path plus the refresh command.

- [ ] **Step 6: Resolve all crawler-owned paths before creating CrawlConfig**

In `scripts/crawl_huiji_res1999.py`, load `get_config()`, choose the CLI credential override only when present, and pass each crawler-owned path through `resolve_project_local_path`. Keep `edge_executable` exempt because it is an approved system program. The parser must have no `--robot-root` option.

The PowerShell launcher must remove `$RobotRoot` and `--robot-root`, optionally accept `[string]$Config = ""`, pass `--config` only when supplied, and replace all GUI instructions with the project-local refresh command or `-Transport Edge` guidance.

- [ ] **Step 7: Run focused and crawler regression tests**

Run:

```powershell
& $Py -m pytest tests/test_huiji_cookies.py tests/test_huiji_cli.py tests/test_huiji_browser_client.py tests/test_huiji_start_script.py -q
rg -n "robot_root|D:\\1999WIKI_ROBOT|GUI tool cookie" src/huijiwiki scripts/crawl_huiji_res1999.py crawl_huiji_res1999.ps1
```

Expected: tests pass; `rg` returns no matches and therefore exit code 1.

---

### Task 3: Safe one-time credential import

**Specs:** MIG-P0-01, MIG-P0-02, MIG-P0-03, MIG-P0-04

**Files:**
- Create: `src/huijiwiki/credential_store.py`
- Create: `scripts/import_huiji_credentials.py`
- Create: `tests/test_huiji_credential_store.py`
- Create: `tests/test_huiji_credential_import_cli.py`

**Interfaces:**
- Produces: `CredentialInspection(path: Path, size: int, sha256: str, cookie_names: tuple[str, ...])`.
- Produces: `inspect_credential(path: Path) -> CredentialInspection`.
- Produces: `atomic_write_validated_credential(target: Path, payload: bytes, *, replace: bool) -> CredentialInspection`.
- Produces: `import_credential(source: Path, target: Path, *, replace: bool = False) -> dict[str, object]`.
- Task 4 reuses `atomic_write_validated_credential`; no second write implementation is allowed.

- [ ] **Step 1: Write failing inspection and import tests**

Cover exact-copy success, same-hash idempotence, different-hash conflict, explicit replacement, malformed/empty source, atomic-write failure and secret redaction. Required assertions include:

```python
report = import_credential(source, target)
assert target.read_bytes() == source.read_bytes()
assert report["source"]["sha256"] == report["target"]["sha256"]
assert report["source"]["size"] == report["target"]["size"]
assert "session-secret" not in json.dumps(report)
```

Monkeypatch `os.replace` to fail and assert an existing target remains byte-identical and no temporary file remains.

- [ ] **Step 2: Write failing CLI target-boundary tests**

The CLI accepts `--source`, `--replace` and an optional project-local `--output` evidence path, but no user-controlled external credential target. Monkeypatch `get_config()` to a temporary project config and assert the target is `cfg.huiji.credential_file`. Assert stdout/file output is canonical JSON and stderr never includes Cookie values.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```powershell
& $Py -m pytest tests/test_huiji_credential_store.py tests/test_huiji_credential_import_cli.py -q
```

Expected: import errors because the modules do not exist.

- [ ] **Step 4: Implement inspection and atomic installation**

Inspection must read bytes once for size/hash and parse via `CookieLoader(path)`. Reports expose only sorted Cookie names:

```python
@dataclass(frozen=True)
class CredentialInspection:
    path: Path
    size: int
    sha256: str
    cookie_names: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "size": self.size,
            "sha256": self.sha256,
            "cookie_names": list(self.cookie_names),
        }
```

Use `tempfile.NamedTemporaryFile(dir=target.parent, delete=False)`, flush, `os.fsync`, validate the temporary file, then `os.replace`. On all exceptions, remove only the temporary file. Never delete or mutate `source`.

- [ ] **Step 5: Implement the import CLI**

The command must load the project credential target from central config, resolve the explicit source without imposing project containment, and emit `json.dumps(report, sort_keys=True, ensure_ascii=False)` to stdout or atomically to a project-local `--output`. Exit codes:

```text
0 imported or already_same_hash
2 target_conflict_without_replace
3 source_missing_or_invalid
4 atomic_write_or_post_validation_failure
```

Do not add the legacy path as a default, example or help-text value.

- [ ] **Step 6: Run focused tests and a synthetic CLI smoke**

Run:

```powershell
& $Py -m pytest tests/test_huiji_credential_store.py tests/test_huiji_credential_import_cli.py -q
$Tmp = Join-Path $env:TEMP 'huiji-credential-import-smoke.dat'
$SmokeTarget = '.local/huiji/credentials/import-smoke.dat'
[IO.File]::WriteAllText(
    $Tmp,
    "huiji_session=synthetic-session`n",
    [Text.UTF8Encoding]::new($false)
)
$PreviousHuijiConfigPath = $env:HUIJI_CONFIG_PATH
try {
    $env:HUIJI_CONFIG_PATH = $SmokeTarget
    & $Py scripts/import_huiji_credentials.py --source $Tmp
    if ($LASTEXITCODE -ne 0) { throw "Synthetic import smoke failed" }
} finally {
    $env:HUIJI_CONFIG_PATH = $PreviousHuijiConfigPath
    Remove-Item -LiteralPath $Tmp -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $SmokeTarget -ErrorAction SilentlyContinue
}
```

Expected: tests pass; CLI writes only a redacted report; the real default credential target is never read or modified by this smoke.

---

### Task 4: Project-local Browser/Edge credential refresh

**Specs:** REFRESH-P0-01, REFRESH-P0-02, REFRESH-P0-03, REFRESH-P0-04, CRED-P0-06

**Files:**
- Create: `src/huijiwiki/credential_refresh.py`
- Create: `scripts/refresh_huiji_credentials.py`
- Modify: `src/huijiwiki/browser_client.py`
- Create: `tests/test_huiji_credential_refresh.py`
- Modify: `tests/test_huiji_browser_client.py`
- Modify: `tests/test_huiji_cli.py`

**Interfaces:**
- Produces: `select_huiji_cookies(raw_cookies: list[dict[str, object]]) -> list[dict[str, object]]`.
- Produces: `serialize_huiji_cookies(raw_cookies: list[dict[str, object]]) -> bytes` using the existing JSON `{"cookies": [...]}` format.
- Produces: `refresh_credentials(client: BrowserApiClient, *, expected_user: str, target: Path) -> dict[str, object]`.
- Consumes: Task 3 `atomic_write_validated_credential`.

- [ ] **Step 1: Write failing cookie selection and serialization tests**

Use fake browser cookies for `res1999.huijiwiki.com`, parent `.huijiwiki.com` and an unrelated domain. Assert unrelated cookies are excluded, values survive only in the serialized private payload, and reports contain only names/hash/size.

- [ ] **Step 2: Write failing account and atomicity tests**

Use fake clients/contexts to cover:

```python
with pytest.raises(AccountMismatchError):
    refresh_credentials(wrong_account_client, expected_user="POTATO BOT", target=target)
assert target.read_bytes() == original
```

Also cover anonymous account, Cloudflare error, empty matching Cookie set, `os.replace` failure and successful replacement. In every failure, the prior target remains unchanged.

- [ ] **Step 3: Write failing CLI transport/path tests**

The refresh CLI accepts only `browser` or `edge`; defaults to `edge`; forces account verification; validates target/out/profile and optional evidence `--output` through Task 1; and closes the client in `finally`. Mock the browser factory and assert no project-external profile is accepted.

- [ ] **Step 4: Run focused tests and verify RED**

Run:

```powershell
& $Py -m pytest tests/test_huiji_credential_refresh.py tests/test_huiji_browser_client.py tests/test_huiji_cli.py -q
```

Expected: missing refresh module/CLI failures.

- [ ] **Step 5: Implement safe browser Cookie export**

Call `client.get_userinfo()` immediately before reading `client.context.cookies([HOMEPAGE_URL])`. Require the returned account to equal `expected_user`. Keep only cookies applicable to `res1999.huijiwiki.com`, preserve `name`, `value`, `domain`, `path`, `expires`, `secure` and `httpOnly`, sort deterministically, and serialize as UTF-8 JSON.

Install through `atomic_write_validated_credential(target, payload, replace=True)`. The result JSON may include target-relative path, size, SHA-256, names and account, but never values. When `--output` is supplied, write canonical JSON atomically without a UTF-8 BOM.

- [ ] **Step 6: Implement refresh CLI and update guidance**

Construct Browser/Edge client config with project-local output/profile and `browser_verify=True`. Use the existing factories:

```python
factory = (
    create_verified_browser_client
    if args.transport == "browser"
    else create_edge_cdp_browser_client
)
client = factory(runtime_config)
try:
    report = refresh_credentials(
        client,
        expected_user=args.expected_user,
        target=cfg.huiji.credential_file,
    )
finally:
    client.close()
```

Update crawler expiry messages and PowerShell prompts to reference this command. Do not automatically refresh or rewrite credentials during a normal crawl.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
& $Py -m pytest tests/test_huiji_credential_refresh.py tests/test_huiji_browser_client.py tests/test_huiji_cli.py tests/test_huiji_start_script.py -q
```

Expected: all pass with no Cookie values in captured output.

---

### Task 5: External-path inventory, allowlist and active documentation

**Specs:** AUDIT-P0-01 through AUDIT-P0-07, BOUND-P0-05

**Files:**
- Create: `src/runtime_path_audit.py`
- Create: `src/runtime_secret_audit.py`
- Create: `config/external-path-allowlist.yaml`
- Create: `scripts/audit_external_paths.py`
- Create: `scripts/audit_credential_secrecy.py`
- Create: `scripts/verify_huiji_project_boundary.py`
- Create: `tests/test_runtime_path_audit.py`
- Create: `tests/test_runtime_secret_audit.py`
- Create: `tests/test_huiji_project_boundary_script.py`
- Modify: `README.md`
- Modify: `docs/huiji-rag-runbook.md`
- Modify: `docs/backend-recovery-strategy.md`
- Modify: `docs/frontend-recovery-strategy.md`
- Modify: `docs/rag-assets.md`
- Modify: `docs/wiki-rag-contract-record.md`
- Create during acceptance: `eval/project-path-audit/<run-id>/external_path_inventory.v1.json`
- Create during acceptance: `eval/project-path-audit/<run-id>/acceptance-summary.md`

**Interfaces:**
- Produces: `audit_external_paths(project_root: Path, policy_path: Path) -> dict[str, object]`.
- Produces canonical report fields: `schema_version`, `project_root`, `scanned_files`, `excluded_scopes`, `matches`, `allowlist_entries`, `unclassified_external_path_count`, `stale_allowlist_count`.
- Produces: `audit_credential_secrecy(project_root: Path, credential_path: Path) -> dict[str, object]`, reporting only violating file and Cookie name.
- Produces: `ForbiddenFileAccess(RuntimeError)` and a generic `--forbid-root` audit-hook wrapper around crawler CLI; it contains no hardcoded legacy path.

- [ ] **Step 1: Write failing scanner tests**

Temporary fixture projects must prove detection of drive absolute paths, UNC paths and `file://` paths; prove HTTP(S) URLs are ignored; prove exact allowlist classification; and fail on broad/stale allowlist entries. Required assertions:

```python
assert report["unclassified_external_path_count"] == 1
assert report["matches"][0]["category"] == "unclassified"
assert "secret-value" not in json.dumps(report)
```

Add a test that `.env`, `.local`, data, volumes, logs, binaries, frontend `dist`, tests and historical specs/plans are represented in `excluded_scopes` and never read for contents.

Add `tests/test_runtime_secret_audit.py` with a synthetic credential and text tree. It must detect an exact Cookie value copied into a visible text file, report only the Cookie name/file, ignore the credential file itself and `.env`, and prove the raw secret is absent from the JSON report.

- [ ] **Step 2: Write failing file-access guard tests**

The generic wrapper installs `sys.addaudithook` before importing/running the crawler entry point. Tests must create an allowed root and a forbidden root, then assert an attempted `open()` under the forbidden root raises a redacted `ForbiddenFileAccess` while project-local reads succeed. Do not move any real directory.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```powershell
& $Py -m pytest tests/test_runtime_path_audit.py tests/test_runtime_secret_audit.py tests/test_huiji_project_boundary_script.py -q
```

Expected: missing audit/secret-audit modules or scripts.

- [ ] **Step 4: Implement deterministic path inventory**

Scan only UTF-8 text in the approved production scope, including all top-level and nested active docs except `docs/superpowers/specs/**` and `docs/superpowers/plans/**`. Use explicit regexes for filesystem paths, not a generic colon match. Sort by normalized relative file, line and value before JSON encoding. The scanner must not open `.env` or `.local`; it must also exclude its own `config/external-path-allowlist.yaml` policy input from match scanning and record that exclusion reason.

The allowlist schema is:

```yaml
schema_version: external_path_allowlist.v1
entries:
  - id: system-edge-x86
    file: src/huijiwiki/browser_client.py
    value: 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    category: system_executable
    reason: Microsoft Edge default installation candidate; not project-owned data.
```

Add equally exact entries for the second Edge candidate, each active diagnostic script's literal local-path leak sentinel, and active documentation whose text explicitly demonstrates that local drive paths are forbidden. Reject duplicate IDs, wildcard files/values, regex values, unmatched entries and categories other than `system_executable` or `diagnostic_sentinel`.

- [ ] **Step 5: Implement CLI and isolation wrapper**

`scripts/audit_external_paths.py` writes canonical JSON to an explicit project-local `--output` and exits 2 for unclassified matches, 3 for stale/invalid allowlist, 0 only for a clean report.

`scripts/audit_credential_secrecy.py` parses the project-local credential in memory, scans visible UTF-8 project text while excluding `.git`, `.env`, `.local`, data/volumes, logs and binaries, and writes only Cookie-name/file violations. It exits 2 if any exact Cookie value appears outside the private credential boundary.

`scripts/verify_huiji_project_boundary.py` accepts repeatable `--forbid-root`, an explicit `--evidence` inside the project, and crawler arguments after `--`. Its audit hook rejects Python `open` events whose resolved path is under a forbidden root, records only the blocked path and event count, and always writes a canonical redacted receipt.

- [ ] **Step 6: Update active documentation**

Rewrite README's active introduction and prerequisites so Huiji crawler-only is the current architecture and no external Obsidian vault is required. Historical notes may remain but must contain no executable instruction using an external project path.

Replace hardcoded `cd`/`Set-Location` commands in backend and frontend recovery documents with `<project-root>`-relative instructions. Convert `docs/rag-assets.md` into a clear legacy tombstone that points to the Huiji runbook and contains no executable Obsidian asset-build command. Change the absolute processed-artifact path in `docs/wiki-rag-contract-record.md` to `data/processed/huiji/dev`.

Add to `docs/huiji-rag-runbook.md`:

```powershell
python scripts/import_huiji_credentials.py --source <explicit-source-config.dat>
python scripts/refresh_huiji_credentials.py --transport edge
.\crawl_huiji_res1999.ps1 -Mode DryRun -Transport Requests
python scripts/audit_external_paths.py --output <project-local-evidence.json>
```

State that real secrets are excluded from source packages and that Browser/Edge is the recovery path when Requests credentials expire.

- [ ] **Step 7: Run scanner tests and current-tree audit**

Run:

```powershell
& $Py -m pytest tests/test_runtime_path_audit.py tests/test_runtime_secret_audit.py tests/test_huiji_project_boundary_script.py -q
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-project-paths'
$RunDir = Join-Path 'eval/project-path-audit' $RunId
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
& $Py scripts/audit_external_paths.py --output (Join-Path $RunDir 'external_path_inventory.v1.json')
```

Expected: exit 0, `unclassified_external_path_count=0`, `stale_allowlist_count=0`. If a new path appears, classify its ownership and remove the dependency or add one exact justified entry; never widen the allowlist to make the gate green.

---

### Task 6: Real credential migration and isolated end-to-end acceptance

**Specs:** all P0 completion criteria

**Files:**
- Create private runtime file: `.local/huiji/credentials/config.dat` (Git-ignored)
- Create evidence: `eval/project-path-audit/<run-id>/credential-import.v1.json`
- Create evidence: `eval/project-path-audit/<run-id>/requests-boundary.v1.json`
- Create evidence: `eval/project-path-audit/<run-id>/edge-boundary.v1.json`
- Create evidence: `eval/project-path-audit/<run-id>/browser-refresh.v1.json`
- Create evidence: `eval/project-path-audit/<run-id>/secret-boundary.v1.json`
- Create evidence: `eval/project-path-audit/<run-id>/test-results.txt`
- Create evidence: `eval/project-path-audit/<run-id>/acceptance-summary.md`

**Interfaces:**
- Consumes the external source only via Task 3's explicit `--source`.
- Consumes Tasks 1-5 tests, path scanner, refresh CLI and file-access guard.
- Produces a redacted evidence bundle; no Cookie values or `.env` contents.

- [ ] **Step 1: Re-inventory the source without exposing contents**

Run:

```powershell
$Source = 'D:\1999WIKI_ROBOT\huijiwiki_bot_gui_v0.3.46\config.dat'
if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Credential source is missing" }
$SourceItem = Get-Item -LiteralPath $Source
$SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
"source_size=$($SourceItem.Length) source_sha256=$SourceHash"
```

Do not print file contents. Stop if the source is missing, empty or changes between pre-inspection and import.

- [ ] **Step 2: Import the real credential and verify exact copy**

Run the importer and redirect its redacted canonical JSON into the current evidence directory:

```powershell
& $Py scripts/import_huiji_credentials.py `
  --source $Source `
  --output (Join-Path $RunDir 'credential-import.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Credential import failed: $LASTEXITCODE" }
$Target = (Resolve-Path -LiteralPath '.local/huiji/credentials/config.dat').Path
$TargetHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant()
if ($SourceHash -ne $TargetHash) { throw "Credential SHA-256 mismatch" }
if ((Get-Item $Source).Length -ne (Get-Item $Target).Length) { throw "Credential size mismatch" }
```

If a different project-local target already exists, stop on conflict, inspect both redacted summaries and use `--replace` only after confirming the external source is the desired current credential.

- [ ] **Step 3: Run Requests dry-run under the old-root access guard**

Run without moving or changing the old directory:

```powershell
$DryRunOut = Join-Path $RunDir 'crawler-dry-run'
& $Py scripts/verify_huiji_project_boundary.py `
  --forbid-root 'D:\1999WIKI_ROBOT' `
  --evidence (Join-Path $RunDir 'requests-boundary.v1.json') `
  -- --dry-run --transport requests --out $DryRunOut
if ($LASTEXITCODE -ne 0) { throw "Isolated Requests dry-run failed: $LASTEXITCODE" }
```

Expected: crawler account is `POTATO BOT`, dry-run succeeds, blocked access count is zero. If the Cookie is expired, do not weaken the gate; complete Step 4 refresh and rerun Step 3.

- [ ] **Step 4: Run real Browser/Edge account verification and refresh**

Use the project-local Edge profile and do not pass `--no-browser-verify`:

```powershell
$PrivateEdgeProfile = '.local\huiji\refresh-runtime\edge_profile'
& $Py scripts/verify_huiji_project_boundary.py `
  --forbid-root 'D:\1999WIKI_ROBOT' `
  --evidence (Join-Path $RunDir 'edge-boundary.v1.json') `
  -- --dry-run --transport edge --out $DryRunOut --edge-profile $PrivateEdgeProfile
if ($LASTEXITCODE -ne 0) { throw "Isolated Edge dry-run failed: $LASTEXITCODE" }

& $Py scripts/refresh_huiji_credentials.py `
  --transport edge `
  --out $DryRunOut `
  --edge-profile $PrivateEdgeProfile `
  --output (Join-Path $RunDir 'browser-refresh.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Edge credential refresh failed: $LASTEXITCODE" }
```

Complete interactive login/Cloudflare verification only if prompted. Verify the report account is `POTATO BOT`, Cookie names are nonempty, and no values appear. Rerun the isolated Requests dry-run after refresh.

The Browser/Edge profile is credential-bearing runtime state. It must remain under `.local/` (or another explicitly ignored private project-local directory) and must never be stored in the evidence bundle.

- [ ] **Step 5: Run targeted and complete tests**

Run:

```powershell
& $Py -m pytest `
  tests/test_huiji_project_paths.py `
  tests/test_config.py `
  tests/test_huiji_cookies.py `
  tests/test_huiji_cli.py `
  tests/test_huiji_start_script.py `
  tests/test_huiji_credential_store.py `
  tests/test_huiji_credential_import_cli.py `
  tests/test_huiji_credential_refresh.py `
  tests/test_huiji_browser_client.py `
  tests/test_runtime_path_audit.py `
  tests/test_runtime_secret_audit.py `
  tests/test_huiji_project_boundary_script.py -q 2>&1 |
  Tee-Object -FilePath (Join-Path $RunDir 'test-results.txt')
if ($LASTEXITCODE -ne 0) { throw "Targeted tests failed" }
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Full Python test suite failed" }
```

Do not claim completion if full-suite failures are dismissed as unrelated without reproducing and classifying them.

- [ ] **Step 6: Run final path and secret boundary checks**

Run the final inventory after all edits. Then verify ignored status and scan Git-visible text without printing secret values. The verification implementation must compare parsed Cookie values in memory and report only violating file plus Cookie name:

```powershell
& $Py scripts/audit_external_paths.py --output (Join-Path $RunDir 'external_path_inventory.v1.json')
if ($LASTEXITCODE -ne 0) { throw "External path audit failed" }
& $Py scripts/audit_credential_secrecy.py `
  --credential .local/huiji/credentials/config.dat `
  --output (Join-Path $RunDir 'secret-boundary.v1.json')
if ($LASTEXITCODE -ne 0) { throw "Credential secrecy audit failed" }
git check-ignore .env .local/huiji/credentials/config.dat
rg -n "robot_root|D:\\1999WIKI_ROBOT|D:\\Obsidian_depot\\Reverse1999" `
  backend config infra scripts src frontend/react-app/src README.md docs/huiji-rag-runbook.md crawl_huiji_res1999.ps1
```

Expected: ignore check lists both private paths; secret audit has zero violations; `rg` has no production match. System Edge and diagnostic sentinel exceptions appear classified in the canonical inventory, not as unclassified.

- [ ] **Step 7: Write the acceptance summary and self-check every Spec ID**

The summary must list:

```text
source/target size and SHA-256 equality (no Cookie values)
credential import status
Requests isolated dry-run status
Browser/Edge verified account and refresh status
path audit counts and allowlist categories
targeted/full test counts
private path ignore status
old source retained and unchanged
P0 Spec ID checklist
P1/P2 explicitly not executed
```

Recompute the external source hash at the end and require it to equal `$SourceHash`. If it differs, stop completion reporting and investigate whether another process refreshed it during acceptance; do not overwrite either copy automatically.

---

## 3. Deferred / Out of Scope

- `CRED-P1-01`: canonical JSON-only steady state and pickle parser removal.
- `CRED-P1-02`: private deployment package switch.
- `REFRESH-P1-01` / `REFRESH-P1-02`: interactive auto-refresh prompt and dedicated refresh evidence schema beyond the P0 report.
- `BOUND-P1-01`: deletion of Obsidian compatibility dataclass/library API.
- `BOUND-P1-02`: unified discovery for Conda, Docker and browser executables.
- `AUDIT-P1-01`: full Python/PowerShell AST semantic path parser.
- `AUDIT-P1-02`: unpacked relocation smoke test for a generated source package.
- All Spec P2 items.

## 4. 完成后自检表

- [ ] `CRED-P0-01` settings 有项目相对凭据路径。
- [ ] `CRED-P0-02` CLI/env/settings/default 优先级测试通过。
- [ ] `CRED-P0-03` resolve 后 containment 和逃逸测试通过。
- [ ] `CRED-P0-04` Requests fail-closed，Browser/Edge 独立。
- [ ] `CRED-P0-05` `.env` 与 `.local` 被忽略且 example 无秘密。
- [ ] `CRED-P0-06` 所有报告和异常脱敏。
- [ ] `CRED-P0-07` CookieLoader 无 robot-root/env 推断。
- [ ] `MIG-P0-01` 只有显式 source 可在项目外。
- [ ] `MIG-P0-02` 真实迁移 hash/size/names 一致且源未改。
- [ ] `MIG-P0-03` 冲突停止与 replace 原子性测试通过。
- [ ] `MIG-P0-04` 导入输出无 Cookie 值。
- [ ] `REFRESH-P0-01` 项目内 Browser/Edge 刷新可运行。
- [ ] `REFRESH-P0-02` 账号/Cloudflare/空 Cookie 失败不改目标。
- [ ] `REFRESH-P0-03` 原子替换失败测试通过。
- [ ] `REFRESH-P0-04` 所有过期提示指向项目内流程。
- [ ] `BOUND-P0-01` 生产代码无旧路径和 robot-root。
- [ ] `BOUND-P0-02` 启动接口无 `--robot-root` / `$RobotRoot`。
- [ ] `BOUND-P0-03` Huiji raw/processed/baseline 与 crawler out/profile 受 containment 门禁保护。
- [ ] `BOUND-P0-04` Obsidian 占位路径项目本地且 CLI 仍 fail-closed。
- [ ] `BOUND-P0-05` 活动文档无旧目录前置条件。
- [ ] `BOUND-P0-06` 旧根访问被阻断时两类 transport 均验收。
- [ ] `AUDIT-P0-01` 扫描范围和排除范围有证据。
- [ ] `AUDIT-P0-02` drive/UNC/file URL 检测与 HTTP 排除测试通过。
- [ ] `AUDIT-P0-03` allowlist 精确且无陈旧项。
- [ ] `AUDIT-P0-04` 只有两种允许类别。
- [ ] `AUDIT-P0-05` canonical JSON 不读取私有文件。
- [ ] `AUDIT-P0-06` 未分类计数和两个旧路径生产命中均为零。
- [ ] `AUDIT-P0-07` 测试调用同一审计实现，历史排除有原因。
- [ ] 全量 Python tests 通过。
- [ ] P1/P2 未进入执行范围。
