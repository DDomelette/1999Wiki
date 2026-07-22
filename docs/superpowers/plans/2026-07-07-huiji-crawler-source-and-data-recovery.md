# Huiji Crawler Source And Data Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the Huiji res1999 crawler toolchain and rebuild the lost raw crawler dataset under `data/huiji/res1999`.

**Architecture:** Recover missing crawler source from Git history, then regenerate raw Wiki text, Data pages, resource manifest, SQLite crawl state, and static assets from the live read-only HuijiWiki API/CDN. Treat existing `data/processed/huiji/dev` as a derived artifact cache only; it must not be used as a substitute for raw crawler data.

**Tech Stack:** Windows PowerShell, Git, Conda environment `1999wiki`, Python 3, pytest, MediaWiki API, Microsoft Edge browser transport, SQLite, JSONL.

## Global Constraints

- Worktree root is `D:\PycharmProjects\nlp`.
- Project root is `D:\PycharmProjects\nlp\LangChain\1999Search`.
- Do not use `git reset --hard`.
- Do not revert unrelated user or recovery changes.
- Do not commit unless the user explicitly asks for commits again.
- Do not print secrets, cookies, passwords, or bot credentials.
- Only crawl `https://res1999.huijiwiki.com/wiki` and `https://res1999.huijiwiki.com/api.php`.
- Only perform read-only MediaWiki API actions.
- Do not attempt to bypass Cloudflare; manual browser verification is allowed.
- Expected bot account is `POTATO BOT`.
- Default raw output root is `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999`.
- Existing `data/processed/huiji/dev` may be used for comparison, but not as authoritative raw source.

---

## Current Evidence

- Raw crawler root currently exists but contains only `edge_profile`.
- Missing raw files include `siteinfo.json`, `pages.jsonl`, `wikitext.jsonl`, `data_pages.jsonl`, `resources_manifest.jsonl`, `crawl_state.sqlite`, `errors.jsonl`, `resource_download_errors.jsonl`, and `assets/files`.
- Current HEAD `acb1d3b4` contains the text/API crawler but does not contain the resource downloader.
- Git commit `69f04ec757ab34a5917f7f5c0d222448ba3257af` contains:
  - `LangChain/1999Search/download_huiji_resources.bat`
  - `LangChain/1999Search/download_huiji_resources.ps1`
  - `LangChain/1999Search/scripts/download_huiji_resources.py`
  - `LangChain/1999Search/src/huijiwiki/resource_downloader.py`
  - `LangChain/1999Search/tests/test_huiji_resource_downloader.py`
- Git history does not contain the lost raw data files or `assets/files`.
- Existing derived artifacts under `data/processed/huiji/dev` currently report:
  - `parent_blocks.jsonl`: 8246 lines
  - `child_blocks.jsonl`: 16010 lines
  - `media_assets.jsonl`: 15758 lines

## Execution Status

- 2026-07-07: Task 1 completed. Baseline snapshot was written to `D:\PycharmProjects\nlp\LangChain\1999Search\recovery-huiji-crawler-baseline.txt`.
- 2026-07-07: Task 2 completed. The missing resource downloader source files were restored from commit `69f04ec757ab34a5917f7f5c0d222448ba3257af`.
- Verification completed: `D:\Anaconda32024\envs\1999wiki\python.exe -m pytest ... -q` reported `68 passed in 2.47s`.
- Live crawl and resource download are intentionally still pending; the user will run those PowerShell commands manually.
- 2026-07-07: Added local-only integrity verification command `.\verify_huiji_res1999.bat`; command details are documented in `D:\PycharmProjects\nlp\LangChain\1999Search\docs\superpowers\specs\2026-07-07-huiji-integrity-verifier-command-reference.md`.

---

## File Structure

Restore from Git:

- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\download_huiji_resources.bat`
  Windows batch wrapper for the resource downloader.
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\download_huiji_resources.ps1`
  PowerShell launcher for the resource downloader.
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\download_huiji_resources.py`
  Python CLI entrypoint for static resource downloads.
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huijiwiki\resource_downloader.py`
  Downloader implementation that reads `crawl_state.sqlite`, writes `assets/files`, validates size and sha1, and updates resource statuses.
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_resource_downloader.py`
  Regression tests for resource download behavior.

Already present crawler files:

- Keep: `D:\PycharmProjects\nlp\LangChain\1999Search\crawl_huiji_res1999.bat`
- Keep: `D:\PycharmProjects\nlp\LangChain\1999Search\crawl_huiji_res1999.ps1`
- Keep: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\crawl_huiji_res1999.py`
- Keep: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huijiwiki\*.py`

Regenerated raw data:

- Recreate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\siteinfo.json`
- Recreate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\pages.jsonl`
- Recreate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\wikitext.jsonl`
- Recreate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\data_pages.jsonl`
- Recreate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\resources_manifest.jsonl`
- Recreate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\crawl_state.sqlite`
- Recreate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\assets\files\...`

---

### Task 1: Confirm Recovery Baseline

**Files:**
- Read: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999`
- Read: `D:\PycharmProjects\nlp\.git`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\recovery-huiji-crawler-baseline.txt`

**Interfaces:**
- Consumes: current filesystem and Git state.
- Produces: human-readable baseline snapshot for later comparison.

- [ ] **Step 1: Record Git HEAD and raw data directory state**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
@(
  "timestamp=$(Get-Date -Format o)"
  "repo=$(git -C D:\PycharmProjects\nlp rev-parse --show-toplevel)"
  "head=$(git -C D:\PycharmProjects\nlp log -1 --oneline --decorate HEAD)"
  "raw_entries="
  (Get-ChildItem -LiteralPath .\data\huiji\res1999 -Force | Format-Table Mode,Length,LastWriteTime,Name -AutoSize | Out-String)
) | Set-Content -LiteralPath .\recovery-huiji-crawler-baseline.txt -Encoding UTF8
```

Expected: `recovery-huiji-crawler-baseline.txt` exists and shows only `edge_profile` under the raw root.

- [ ] **Step 2: Confirm raw crawler files are absent**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
@'
from pathlib import Path
root = Path(r"D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999")
required = [
    "siteinfo.json",
    "pages.jsonl",
    "wikitext.jsonl",
    "data_pages.jsonl",
    "resources_manifest.jsonl",
    "crawl_state.sqlite",
    "assets/files",
]
for rel in required:
    p = root / rel
    print(rel, "present" if p.exists() else "missing")
'@ | D:\Anaconda32024\envs\1999wiki\python.exe -
```

Expected: each required raw crawler artifact prints `missing`.

- [ ] **Step 3: Confirm Git history has downloader source but not raw data**

Run:

```powershell
cd D:\PycharmProjects\nlp
git ls-tree -r --name-only 69f04ec757ab34a5917f7f5c0d222448ba3257af -- LangChain/1999Search |
  Select-String -Pattern "download_huiji_resources|resource_downloader|test_huiji_resource_downloader"

git log --all --name-only --pretty=format:"COMMIT %H %s" -- `
  LangChain/1999Search/data/huiji/res1999/wikitext.jsonl `
  LangChain/1999Search/data/huiji/res1999/resources_manifest.jsonl `
  LangChain/1999Search/data/huiji/res1999/crawl_state.sqlite `
  LangChain/1999Search/data/huiji/res1999/assets/files
```

Expected: first command lists the downloader files; second command prints no commits for raw data.

### Task 2: Restore Missing Resource Downloader Source

**Files:**
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\download_huiji_resources.bat`
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\download_huiji_resources.ps1`
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\scripts\download_huiji_resources.py`
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\src\huijiwiki\resource_downloader.py`
- Restore: `D:\PycharmProjects\nlp\LangChain\1999Search\tests\test_huiji_resource_downloader.py`

**Interfaces:**
- Consumes: Git commit `69f04ec757ab34a5917f7f5c0d222448ba3257af`.
- Produces: runnable resource downloader command `.\download_huiji_resources.bat`.

- [ ] **Step 1: Restore downloader files from Git history**

Run:

```powershell
cd D:\PycharmProjects\nlp
git restore --source 69f04ec757ab34a5917f7f5c0d222448ba3257af -- `
  LangChain/1999Search/download_huiji_resources.bat `
  LangChain/1999Search/download_huiji_resources.ps1 `
  LangChain/1999Search/scripts/download_huiji_resources.py `
  LangChain/1999Search/src/huijiwiki/resource_downloader.py `
  LangChain/1999Search/tests/test_huiji_resource_downloader.py
```

Expected: all five files exist in `D:\PycharmProjects\nlp\LangChain\1999Search`.

- [ ] **Step 2: Verify restored files are present**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
Test-Path .\download_huiji_resources.bat
Test-Path .\download_huiji_resources.ps1
Test-Path .\scripts\download_huiji_resources.py
Test-Path .\src\huijiwiki\resource_downloader.py
Test-Path .\tests\test_huiji_resource_downloader.py
```

Expected: five `True` lines.

- [ ] **Step 3: Run crawler and downloader tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest `
  tests\test_huiji_client.py `
  tests\test_huiji_cookies.py `
  tests\test_huiji_state.py `
  tests\test_huiji_jsonl.py `
  tests\test_huiji_models.py `
  tests\test_huiji_pipeline.py `
  tests\test_huiji_cli.py `
  tests\test_huiji_browser_client.py `
  tests\test_huiji_start_script.py `
  tests\test_huiji_resource_downloader.py `
  -q
```

Expected: all selected tests pass.

### Task 3: Verify Browser Session Before Crawling

**Files:**
- Reads and writes only crawler profile/cache files under `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\edge_profile`.

**Interfaces:**
- Consumes: restored crawler source and the local Edge browser.
- Produces: verified read-only API session for account `POTATO BOT`.

- [ ] **Step 1: Run DryRun through Edge transport**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda activate 1999wiki
.\crawl_huiji_res1999.bat -Mode DryRun -Transport Edge -EdgePort 9333
```

Expected: script verifies `POTATO BOT` and prints a JSON summary with `"dry_run": true`.

- [ ] **Step 2: If account is not POTATO BOT, refresh login in the opened Edge window**

Run the same command again after logging into the bot account:

```powershell
.\crawl_huiji_res1999.bat -Mode DryRun -Transport Edge -EdgePort 9333
```

Expected: no crawl proceeds until the browser API account is `POTATO BOT`.

### Task 4: Rebuild Raw Text, Data Pages, Resource Manifest, And SQLite State

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\siteinfo.json`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\pages.jsonl`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\wikitext.jsonl`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\data_pages.jsonl`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\resources_manifest.jsonl`
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\crawl_state.sqlite`
- Create or append: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\errors.jsonl`

**Interfaces:**
- Consumes: MediaWiki read-only API through Edge transport.
- Produces: authoritative raw crawler dataset used by downstream RAG/Wiki builders.

- [ ] **Step 1: Run a small crawl smoke test**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda activate 1999wiki
.\crawl_huiji_res1999.bat -Mode Small -Transport Edge -EdgePort 9333 -Limit 20
```

Expected: command exits `0`, writes `wikitext.jsonl`, `resources_manifest.jsonl`, and `crawl_state.sqlite`.

- [ ] **Step 2: Validate small crawl output structure**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
@'
from pathlib import Path
root = Path(r"D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999")
for name in ["siteinfo.json", "pages.jsonl", "wikitext.jsonl", "data_pages.jsonl", "resources_manifest.jsonl", "crawl_state.sqlite"]:
    p = root / name
    print(name, p.exists(), p.stat().st_size if p.exists() else 0)
'@ | D:\Anaconda32024\envs\1999wiki\python.exe -
```

Expected: listed files exist; `wikitext.jsonl`, `resources_manifest.jsonl`, and `crawl_state.sqlite` have nonzero size.

- [ ] **Step 3: Run full raw crawler**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda activate 1999wiki
.\crawl_huiji_res1999.bat -Mode Full -Transport Edge -EdgePort 9333
```

Expected: command exits `0`. Previous known-good baseline was approximately `79053` indexed pages, `79032` fetched revisions, and `61087` resources indexed.

- [ ] **Step 4: Validate full raw crawler counts**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
@'
import sqlite3
from pathlib import Path
root = Path(r"D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999")
db = root / "crawl_state.sqlite"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
print("pages", con.execute("select count(*) from pages").fetchone()[0])
print("revisions", con.execute("select count(*) from revisions").fetchone()[0])
print("resources", con.execute("select count(*) from resources").fetchone()[0])
print("pages_by_ns")
for row in con.execute("select ns, count(*) from pages group by ns order by ns"):
    print(row)
con.close()
for name in ["siteinfo.json", "pages.jsonl", "wikitext.jsonl", "data_pages.jsonl", "resources_manifest.jsonl"]:
    p = root / name
    print(name, p.exists(), p.stat().st_size if p.exists() else 0)
'@ | D:\Anaconda32024\envs\1999wiki\python.exe -
```

Expected:

- `pages` is at least `78000`.
- `revisions` is at least `78000`.
- `resources` is at least `60000`.
- Namespace rows include `0`, `10`, `14`, `828`, and `3500`.
- The JSON/JSONL files exist and have nonzero sizes.

### Task 5: Redownload Static Resources

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\assets\files\...`
- Create or append: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\resource_download_errors.jsonl`
- Update: `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999\crawl_state.sqlite`

**Interfaces:**
- Consumes: `resources` table in `crawl_state.sqlite`.
- Produces: downloaded and validated static image/audio/video files.

- [ ] **Step 1: Run limited resource download smoke test**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda activate 1999wiki
.\download_huiji_resources.bat -Workers 2 -Limit 10
```

Expected: command exits `0`; at least 10 resources are marked `downloaded` or skipped as already valid.

- [ ] **Step 2: Download all remaining resources**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda activate 1999wiki
.\download_huiji_resources.bat -Workers 2
```

Expected: command processes all resources. Previous known-good resource size was about `19.13 GB`.

- [ ] **Step 3: Retry failed resources with single worker**

Run this if the previous command exits with code `1` or prints failed resources:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
conda activate 1999wiki
.\download_huiji_resources.bat -Workers 1 -IncludeFailed
```

Expected: failed count reaches `0`, or remaining failures are listed in `resource_download_errors.jsonl` for manual review.

- [ ] **Step 4: Validate resource database status and local paths**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
@'
import sqlite3
from pathlib import Path
root = Path(r"D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999")
con = sqlite3.connect(f"file:{root/'crawl_state.sqlite'}?mode=ro", uri=True, timeout=5)
rows = list(con.execute("select coalesce(download_status,'not_downloaded'), count(*), coalesce(sum(size),0) from resources group by coalesce(download_status,'not_downloaded') order by 1"))
for row in rows:
    print(row)
missing = []
for title, rel in con.execute("select title, local_relpath from resources where download_status='downloaded'"):
    if rel and not (root / rel).exists():
        missing.append((title, rel))
con.close()
print("missing_downloaded_paths", len(missing))
for item in missing[:20]:
    print(item)
'@ | D:\Anaconda32024\envs\1999wiki\python.exe -
```

Expected:

- One status row is `downloaded`.
- `missing_downloaded_paths` is `0`.
- Total resource size is close to the current remote manifest and may differ from the old `19.13 GB` baseline if the Wiki changed.

### Task 6: Rebuild Derived Huiji Corpus And Wiki Data

**Files:**
- Regenerate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji\dev\parent_blocks.jsonl`
- Regenerate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji\dev\child_blocks.jsonl`
- Regenerate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji\dev\media_assets.jsonl`
- Regenerate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji\dev\build_manifest.json`
- Regenerate: `D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji\dev\build_report.json`

**Interfaces:**
- Consumes: raw crawler data and local resources.
- Produces: processed artifacts for Wiki/RAG systems.

- [ ] **Step 1: Rebuild Huiji corpus if the script exists**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
if (Test-Path .\scripts\build_huiji_corpus.py) {
  D:\Anaconda32024\envs\1999wiki\python.exe .\scripts\build_huiji_corpus.py
} else {
  Write-Host "[skip] scripts\build_huiji_corpus.py is not present in this worktree"
}
```

Expected if script exists: `parent_blocks.jsonl`, `child_blocks.jsonl`, `media_assets.jsonl`, `build_manifest.json`, and `build_report.json` are regenerated.

- [ ] **Step 2: Validate processed artifact counts**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
@'
from pathlib import Path
root = Path(r"D:\PycharmProjects\nlp\LangChain\1999Search\data\processed\huiji\dev")
for name in ["parent_blocks.jsonl", "child_blocks.jsonl", "media_assets.jsonl"]:
    p = root / name
    if p.exists():
        with p.open("rb") as f:
            lines = sum(1 for _ in f)
        print(name, lines, p.stat().st_size)
    else:
        print(name, "missing")
'@ | D:\Anaconda32024\envs\1999wiki\python.exe -
```

Expected: line counts are in the same order of magnitude as the pre-loss derived cache: parent blocks around `8246`, child blocks around `16010`, and media assets around `15758`, adjusted for current Wiki changes.

- [ ] **Step 3: Rebuild Wiki database and shared media if the script exists**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
if (Test-Path .\scripts\build_huiji_wiki.py) {
  D:\Anaconda32024\envs\1999wiki\python.exe .\scripts\build_huiji_wiki.py
} else {
  Write-Host "[skip] scripts\build_huiji_wiki.py is not present in this worktree"
}
```

Expected if script exists: Wiki MySQL/MinIO build completes without `media_missing_local_files` spikes caused by missing `assets/files`.

### Task 7: Final Verification And Recovery Report

**Files:**
- Create: `D:\PycharmProjects\nlp\LangChain\1999Search\recovery-huiji-crawler-final.txt`

**Interfaces:**
- Consumes: raw crawler data, restored downloader source, and processed artifacts.
- Produces: final status report for future recovery decisions.

- [ ] **Step 1: Run targeted crawler test suite**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest `
  tests\test_huiji_client.py `
  tests\test_huiji_cookies.py `
  tests\test_huiji_state.py `
  tests\test_huiji_jsonl.py `
  tests\test_huiji_models.py `
  tests\test_huiji_pipeline.py `
  tests\test_huiji_cli.py `
  tests\test_huiji_browser_client.py `
  tests\test_huiji_start_script.py `
  tests\test_huiji_resource_downloader.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Write final recovery summary**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
@'
import sqlite3
from pathlib import Path
from datetime import datetime
root = Path(r"D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999")
db = root / "crawl_state.sqlite"
lines = [f"timestamp={datetime.now().isoformat()}"]
if db.exists():
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    for table in ["pages", "revisions", "resources"]:
        lines.append(f"{table}={con.execute(f'select count(*) from {table}').fetchone()[0]}")
    for row in con.execute("select coalesce(download_status,'not_downloaded'), count(*), coalesce(sum(size),0) from resources group by coalesce(download_status,'not_downloaded') order by 1"):
        lines.append(f"resource_status={row}")
    con.close()
else:
    lines.append("crawl_state.sqlite=missing")
for rel in ["siteinfo.json", "pages.jsonl", "wikitext.jsonl", "data_pages.jsonl", "resources_manifest.jsonl", "crawl_state.sqlite", "assets/files"]:
    p = root / rel
    lines.append(f"{rel}={'present' if p.exists() else 'missing'}")
Path("recovery-huiji-crawler-final.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
'@ | D:\Anaconda32024\envs\1999wiki\python.exe -
Get-Content .\recovery-huiji-crawler-final.txt
```

Expected: final report shows raw files present, nonzero counts for pages/revisions/resources, and resource status dominated by `downloaded`.

---

## Execution Notes

- If `DryRun` fails because the browser API user is not `POTATO BOT`, stop crawling and refresh the bot login in the Edge window.
- If Cloudflare verification appears, complete verification manually in Edge, then rerun the same command.
- If the full text crawl is interrupted, rerun the same `Full` command; it uses SQLite resume state.
- If resource download is interrupted, rerun `.\download_huiji_resources.bat -Workers 2`; completed validated files are skipped.
- If only a few resource downloads fail, rerun `.\download_huiji_resources.bat -Workers 1 -IncludeFailed`.
- If raw crawl is restored successfully, do not delete `data/processed/huiji/dev`; rebuild it only after raw verification passes.
- Because the user currently does not want commits, this plan intentionally uses verification reports instead of commit steps.

## Self-Review

Spec coverage:

- Read-only crawler behavior is covered by Tasks 3 and 4.
- Lost resource downloader recovery is covered by Task 2.
- Full raw text/data/manifest/SQLite regeneration is covered by Task 4.
- Static asset regeneration is covered by Task 5.
- Derived corpus regeneration is covered by Task 6.
- Verification and audit trail are covered by Tasks 1 and 7.

Placeholder scan:

- This plan contains no unresolved placeholder markers, no deferred implementation placeholders, and no unspecified test command.

Type and path consistency:

- Raw root path is consistently `D:\PycharmProjects\nlp\LangChain\1999Search\data\huiji\res1999`.
- Restored source paths consistently use Git root `D:\PycharmProjects\nlp` and project subpath `LangChain/1999Search`.
- Resource downloader commands consistently use `download_huiji_resources.bat`.
