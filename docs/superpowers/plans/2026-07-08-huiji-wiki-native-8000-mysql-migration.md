# Huiji Wiki Native 8000 And MySQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user has requested no subagents for recent Wiki work unless explicitly changed.

**Goal:** Make Wiki a native `:8000` module, stop formal use of `:8001`, add Wiki health checks, and migrate `reverse1999_wiki` into project-owned Docker MySQL by dump/restore.

**Architecture:** FastAPI `backend.main:app` remains the single backend entry. Wiki routes stay under `/api/wiki/*`, read only from MySQL, and do not touch RAG `_state`, Milvus, vectorization, or MinIO writes. MySQL migration is isolated to `reverse1999_wiki`, keeps `edurag-mysql` as rollback source, and switches `.env` only after row-count verification.

**Tech Stack:** FastAPI, Pydantic, PyMySQL, React, Vite, Vitest, pytest, Docker Compose, MySQL 8.0, MinIO HTTP URLs.

## Global Constraints

- `/api/wiki/*` must be served by `backend.main:app` on `http://127.0.0.1:8000`.
- `8001` is not a formal runtime dependency after this plan.
- Do not call `reset_config_for_test()` or clear `get_config()` cache in runtime Wiki requests.
- Do not reset RAG `_state` from Wiki code.
- Configuration changes require restarting `:8000`.
- Wiki router must not call `_ensure_loaded()`.
- Wiki must not read Milvus, rebuild indexes, write processed artifacts, upload MinIO objects, delete MinIO objects, or scan MinIO to infer resources.
- MySQL migration must use dump/restore, not Docker volume copying.
- Migration only targets `reverse1999_wiki`.
- Keep `edurag-mysql` running as rollback source until all gates pass.

---

## 1. Scope

This plan includes:

- `NATIVE-P0-01` to `NATIVE-P0-07`
- `PROXY-P0-01` to `PROXY-P0-03`
- `MYSQL-P0-01` to `MYSQL-P0-08`
- `MEDIA-RAG-P0-01` to `MEDIA-RAG-P0-04`
- `VERIFY-NATIVE-P0-01` to `VERIFY-NATIVE-P0-08`

This plan does not include:

- Wiki builder rerun.
- RAG data rebuild.
- Milvus collection changes.
- MinIO migration.
- `/health` schema extension.
- Docker production hardening beyond adding a project MySQL service.

## 2. File Structure

- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`  
  Add `GET /api/wiki/health`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`  
  Add `WikiHealthResponse`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`  
  Add read-only health/count method.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`  
  Test `/api/wiki/health`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`  
  Test repository health query.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/vite.config.ts`  
  Default `/api/wiki` to `apiTarget`, retaining optional override.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/docker-compose.yml`  
  Add project-owned MySQL service on `3307:3306`.
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/.env.example`  
  Document MySQL variables.
- Add: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/migrate_wiki_mysql.ps1`  
  Dump/restore migration script with row-count verification.
- Add: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_wiki_mysql_migration_script.py`  
  Static safety tests for migration script.

## 3. Hard Acceptance Gates

| Gate | Verification | Failure means |
|---|---|---|
| `GATE-NATIVE-01` | `GET http://127.0.0.1:8000/api/wiki/health` returns `ready: true`, `pageCount > 0` | Wiki is not native on 8000 |
| `GATE-NATIVE-02` | `GET http://127.0.0.1:8000/api/wiki/pages?limit=3` returns non-empty `items` | Wiki data is unavailable on 8000 |
| `GATE-NATIVE-03` | Stop `8001`, then `/wiki` still loads real pages through `5173 -> 8000` | Frontend still depends on 8001 |
| `GATE-NATIVE-04` | After restarting 8000, `/api/wiki/health` responds within the agreed startup timeout | RAG startup dependency is blocking native Wiki |
| `GATE-RAG-01` | `/health` and one `/ask` or `/ask/stream` smoke test reviewed | Wiki merge broke RAG |
| `GATE-MYSQL-01` | Source and target row counts match for core `wiki_*` tables | MySQL migration is incomplete |
| `GATE-MEDIA-01` | Wiki E2E reports `local path leak count: 0` and HTTP media URLs present | Media contract regressed |
| `GATE-ROLLBACK-01` | Old `edurag-mysql` remains running until all gates pass | No rollback source |

## 4. Tasks

### Task 1: Add Wiki Health API

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/backend/wiki_schemas.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/src/huiji_wiki/repository.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_api.py`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_huiji_wiki_repository.py`

**Interfaces:**
- Consumes: existing `MySQLWikiRepository`.
- Produces: `GET /api/wiki/health -> WikiHealthResponse`.

- [ ] **Step 1: Write repository health failing test**

Add to `tests/test_huiji_wiki_repository.py`:

```python
def test_get_health_counts_core_wiki_tables():
    cursor = RecordingCursor(
        one_rows=[
            {"count": 132},
            {"count": 1},
            {"count": 15398},
            {"count": 998},
            {"count": 263},
        ]
    )
    repo = _repo_with_cursor(cursor)

    health = repo.get_health()

    assert health == {
        "ready": True,
        "pageCount": 132,
        "categoryCount": 1,
        "mediaLinkCount": 15398,
        "linkSpanCount": 998,
        "aliasCount": 263,
        "error": "",
    }
    assert all("COUNT(*)" in call[0] for call in cursor.calls)
```

- [ ] **Step 2: Run repository test and verify failure**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_repository.py::test_get_health_counts_core_wiki_tables -q
```

Expected:

```text
FAILED with AttributeError: 'MySQLWikiRepository' object has no attribute 'get_health'
```

- [ ] **Step 3: Implement repository health**

Add to `WikiRepository` protocol:

```python
def get_health(self) -> dict[str, Any]: ...
```

Add to `MySQLWikiRepository`:

```python
def get_health(self) -> dict[str, Any]:
    self.ensure_schema()
    tables = [
        ("pageCount", "wiki_pages"),
        ("categoryCount", "wiki_categories"),
        ("mediaLinkCount", "wiki_media_links"),
        ("linkSpanCount", "wiki_link_spans"),
        ("aliasCount", "wiki_aliases"),
    ]
    payload: dict[str, Any] = {
        "ready": False,
        "pageCount": 0,
        "categoryCount": 0,
        "mediaLinkCount": 0,
        "linkSpanCount": 0,
        "aliasCount": 0,
        "error": "",
    }
    try:
        with self._connect() as conn, conn.cursor() as cur:
            for key, table in tables:
                cur.execute(f"SELECT COUNT(*) AS count FROM {table}")
                row = cur.fetchone() or {}
                payload[key] = int(row.get("count", 0) or 0)
        payload["ready"] = payload["pageCount"] > 0
    except Exception as exc:
        payload["error"] = exc.__class__.__name__
    return payload
```

- [ ] **Step 4: Add schema and API test**

Add to `backend/wiki_schemas.py`:

```python
class WikiHealthResponse(BaseModel):
    ready: bool
    pageCount: int = 0
    categoryCount: int = 0
    mediaLinkCount: int = 0
    linkSpanCount: int = 0
    aliasCount: int = 0
    error: str = ""
```

Extend `FakeRepo` in `tests/test_huiji_wiki_api.py`:

```python
def get_health(self):
    return {
        "ready": True,
        "pageCount": 132,
        "categoryCount": 1,
        "mediaLinkCount": 15398,
        "linkSpanCount": 998,
        "aliasCount": 263,
        "error": "",
    }
```

Add test:

```python
def test_wiki_health_reports_mysql_counts_without_touching_rag(monkeypatch):
    client = _client(monkeypatch)

    payload = client.get("/api/wiki/health").json()

    assert payload["ready"] is True
    assert payload["pageCount"] == 132
    assert payload["mediaLinkCount"] == 15398
```

Add route in `backend/wiki.py`:

```python
@router.get("/health", response_model=WikiHealthResponse)
async def wiki_health() -> WikiHealthResponse:
    return WikiHealthResponse(**get_wiki_repository().get_health())
```

- [ ] **Step 5: Verify health tests**

Run:

```powershell
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py -q
```

Expected:

```text
all tests pass
```

### Task 2: Make Vite Wiki Proxy Native To 8000

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/frontend/react-app/vite.config.ts`

**Interfaces:**
- Consumes: `VITE_API_TARGET`, optional `VITE_WIKI_API_TARGET`.
- Produces: `/api/wiki` proxy defaults to `apiTarget`.

- [ ] **Step 1: Update proxy default**

Change:

```ts
const wikiApiTarget = process.env.VITE_WIKI_API_TARGET || 'http://127.0.0.1:8001'
```

To:

```ts
const wikiApiTarget = process.env.VITE_WIKI_API_TARGET || apiTarget
```

- [ ] **Step 2: Verify frontend tests and build**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/api/wiki.test.ts src/components/wiki/WikiShell.test.tsx
npm run build
```

Expected:

```text
tests pass
Vite build succeeds
```

### Task 3: Add Project-Owned MySQL Service

**Files:**
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/infra/milvus/docker-compose.yml`
- Modify: `D:/PycharmProjects/nlp/LangChain/1999Search/.env.example`

**Interfaces:**
- Produces: Docker service `mysql` with container `reverse1999-main-mysql`.

- [ ] **Step 1: Add MySQL service to compose**

Append under `services:` in `infra/milvus/docker-compose.yml`:

```yaml
  mysql:
    container_name: reverse1999-main-mysql
    image: mysql:8.0
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-123456}
      MYSQL_DATABASE: reverse1999_wiki
    ports:
      - "3307:3306"
    volumes:
      - ./volumes/mysql:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-uroot", "-p$${MYSQL_ROOT_PASSWORD}"]
      interval: 30s
      timeout: 20s
      retries: 5
```

- [ ] **Step 2: Document environment variables**

Add to `.env.example`:

```env
# Wiki MySQL. Dev migration target uses 3307 to avoid edurag-mysql on 3306.
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_DATABASE=reverse1999_wiki
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_ROOT_PASSWORD=123456
```

- [ ] **Step 3: Start target MySQL**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\infra\milvus
docker compose up -d mysql
docker ps --filter "name=reverse1999-main-mysql"
```

Expected:

```text
reverse1999-main-mysql is running or healthy
```

### Task 4: Add Safe Wiki MySQL Migration Script

**Files:**
- Add: `D:/PycharmProjects/nlp/LangChain/1999Search/scripts/migrate_wiki_mysql.ps1`
- Add: `D:/PycharmProjects/nlp/LangChain/1999Search/tests/test_wiki_mysql_migration_script.py`

**Interfaces:**
- Consumes: Docker source container `edurag-mysql`, target container `reverse1999-main-mysql`.
- Produces: backup SQL file under `backups/wiki-mysql/` and restored `reverse1999_wiki` in target MySQL.

- [ ] **Step 1: Write static safety test**

Create `tests/test_wiki_mysql_migration_script.py`:

```python
from pathlib import Path


def test_wiki_mysql_migration_script_uses_dump_restore_not_volume_copy():
    script = Path("scripts/migrate_wiki_mysql.ps1").read_text(encoding="utf-8")

    assert "mysqldump" in script
    assert "reverse1999_wiki" in script
    assert "docker cp" not in script
    assert "Remove-Item" not in script
    assert "DROP DATABASE" not in script
    assert "edurag-mysql" in script
    assert "reverse1999-main-mysql" in script


def test_wiki_mysql_migration_script_does_not_default_source_password():
    script = Path("scripts/migrate_wiki_mysql.ps1").read_text(encoding="utf-8")

    assert 'SourceRootPassword = "123456"' not in script
    assert "Resolve-RootPassword" in script
    assert "SOURCE_MYSQL_ROOT_PASSWORD" in script
```

- [ ] **Step 2: Run static safety test and verify failure**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_wiki_mysql_migration_script.py -q
```

Expected:

```text
FAILED because scripts/migrate_wiki_mysql.ps1 does not exist
```

- [ ] **Step 3: Create migration script**

Create `scripts/migrate_wiki_mysql.ps1`:

```powershell
param(
  [string]$SourceContainer = "edurag-mysql",
  [string]$TargetContainer = "reverse1999-main-mysql",
  [string]$Database = "reverse1999_wiki",
  [string]$SourceRootPassword = "",
  [string]$TargetRootPassword = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backupDir = Join-Path $projectRoot "backups\wiki-mysql"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpPath = Join-Path $backupDir "$Database-$stamp.sql"

function Get-ContainerEnvValue {
  param(
    [string]$Container,
    [string]$Name
  )

  $line = docker inspect $Container --format '{{range .Config.Env}}{{println .}}{{end}}' |
    Where-Object { $_ -like "$Name=*" } |
    Select-Object -First 1

  if ([string]::IsNullOrWhiteSpace($line)) {
    return ""
  }

  return $line.Substring($Name.Length + 1)
}

function Resolve-RootPassword {
  param(
    [string]$Container,
    [string]$ProvidedPassword,
    [string]$EnvName
  )

  if (-not [string]::IsNullOrWhiteSpace($ProvidedPassword)) {
    return $ProvidedPassword
  }

  $envPassword = [Environment]::GetEnvironmentVariable($EnvName)
  if (-not [string]::IsNullOrWhiteSpace($envPassword)) {
    return $envPassword
  }

  $containerPassword = Get-ContainerEnvValue -Container $Container -Name "MYSQL_ROOT_PASSWORD"
  if (-not [string]::IsNullOrWhiteSpace($containerPassword)) {
    return $containerPassword
  }

  throw "Root password for $Container is required. Pass a parameter, set $EnvName, or expose MYSQL_ROOT_PASSWORD in the Docker container environment."
}

$SourceRootPassword = Resolve-RootPassword -Container $SourceContainer -ProvidedPassword $SourceRootPassword -EnvName "SOURCE_MYSQL_ROOT_PASSWORD"
$TargetRootPassword = Resolve-RootPassword -Container $TargetContainer -ProvidedPassword $TargetRootPassword -EnvName "MYSQL_ROOT_PASSWORD"

function Invoke-MysqlScalar {
  param(
    [string]$Container,
    [string]$Password,
    [string]$Sql
  )
  $output = docker exec $Container mysql -uroot "-p$Password" -N -B -e $Sql
  return ($output | Select-Object -Last 1).Trim()
}

Write-Host "Checking source database..."
$sourcePages = Invoke-MysqlScalar -Container $SourceContainer -Password $SourceRootPassword -Sql "SELECT COUNT(*) FROM $Database.wiki_pages;"
if ([int]$sourcePages -le 0) {
  throw "Source database $Database has no wiki_pages rows."
}

Write-Host "Dumping $Database from $SourceContainer to $dumpPath"
docker exec $SourceContainer mysqldump -uroot "-p$SourceRootPassword" --single-transaction --default-character-set=utf8mb4 $Database | Set-Content -Encoding UTF8 -Path $dumpPath

Write-Host "Creating target database if needed..."
docker exec $TargetContainer mysql -uroot "-p$TargetRootPassword" -e "CREATE DATABASE IF NOT EXISTS $Database CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

Write-Host "Restoring dump into $TargetContainer..."
Get-Content -Raw -Encoding UTF8 $dumpPath | docker exec -i $TargetContainer mysql -uroot "-p$TargetRootPassword" $Database

$tables = @("wiki_pages", "wiki_categories", "wiki_media_links", "wiki_link_spans", "wiki_aliases")
foreach ($table in $tables) {
  $sourceCount = Invoke-MysqlScalar -Container $SourceContainer -Password $SourceRootPassword -Sql "SELECT COUNT(*) FROM $Database.$table;"
  $targetCount = Invoke-MysqlScalar -Container $TargetContainer -Password $TargetRootPassword -Sql "SELECT COUNT(*) FROM $Database.$table;"
  Write-Host "$table source=$sourceCount target=$targetCount"
  if ($sourceCount -ne $targetCount) {
    throw "Row count mismatch for $table"
  }
}

Write-Host "Migration verified. Dump retained at $dumpPath"
```

- [ ] **Step 4: Verify static safety test**

Run:

```powershell
python -m pytest tests/test_wiki_mysql_migration_script.py -q
```

Expected:

```text
1 passed
```

### Task 5: Execute MySQL Dump/Restore Migration

**Files:**
- Runtime only: `D:/PycharmProjects/nlp/LangChain/1999Search/backups/wiki-mysql/*.sql`
- Runtime only: local `.env` may be changed after verification.

**Interfaces:**
- Consumes: `edurag-mysql:3306/reverse1999_wiki`.
- Produces: `reverse1999-main-mysql:3307/reverse1999_wiki`.

- [ ] **Step 1: Verify both MySQL containers**

Run:

```powershell
docker ps --filter "name=edurag-mysql"
docker ps --filter "name=reverse1999-main-mysql"
```

Expected:

```text
both containers are running
```

- [ ] **Step 2: Run migration script**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
$env:SOURCE_MYSQL_ROOT_PASSWORD = "<edurag-mysql root password from .env, Docker env, or user-provided value>"
$env:MYSQL_ROOT_PASSWORD = "<reverse1999-main-mysql root password from this project .env>"
powershell -ExecutionPolicy Bypass -File scripts\migrate_wiki_mysql.ps1
```

Do not run this step if the source password is unknown. The script may also read `MYSQL_ROOT_PASSWORD` from the source Docker container environment, but it must not assume `123456` for `edurag-mysql`.

Expected:

```text
wiki_pages source=<same> target=<same>
wiki_categories source=<same> target=<same>
wiki_media_links source=<same> target=<same>
wiki_link_spans source=<same> target=<same>
wiki_aliases source=<same> target=<same>
Migration verified.
```

- [ ] **Step 3: Do not stop source MySQL**

Run:

```powershell
docker ps --filter "name=edurag-mysql"
```

Expected:

```text
edurag-mysql is still running
```

### Task 6: Switch 8000 To Project MySQL

**Files:**
- Modify local runtime file: `D:/PycharmProjects/nlp/LangChain/1999Search/.env`

**Interfaces:**
- Consumes: migrated target DB on `127.0.0.1:3307`.
- Produces: 8000 reads Wiki data from project MySQL.

- [ ] **Step 1: Update local `.env`**

Ensure local `.env` contains:

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_DATABASE=reverse1999_wiki
MYSQL_USER=root
MYSQL_PASSWORD=123456
```

Do not remove API keys already present in `.env`.

- [ ] **Step 2: Stop 8001 Wiki-only process**

Run:

```powershell
$conn = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```

Expected:

```text
No process listens on 8001
```

- [ ] **Step 3: Restart 8000**

Stop the old 8000 process and start:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8000
```

### Task 7: Full Native 8000 Verification

**Files:**
- No production file changes.

**Interfaces:**
- Consumes: running FastAPI `:8000`, Vite `:5173`, project MySQL `:3307`, MinIO `:9002`, RAG services.
- Produces: final acceptance record.

- [ ] **Step 1: Verify Wiki native health and startup timeout**

Run:

```powershell
$deadline = (Get-Date).AddSeconds(60)
$response = $null
do {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/wiki/health" -TimeoutSec 5
    break
  } catch {
    Start-Sleep -Seconds 2
  }
} while ((Get-Date) -lt $deadline)

if ($null -eq $response) {
  throw "8000 did not expose /api/wiki/health within 60 seconds after restart."
}

$response.Content
```

Expected:

```json
{"ready":true,"pageCount":132,...}
```

If 8000 startup stalls because RAG initialization is waiting on Milvus or another dependency, this gate fails. Do not mark the native 8000 merge complete until the startup behavior is understood or the dependency is restored.

- [ ] **Step 2: Verify Wiki pages on 8000**

Run:

```powershell
(Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/wiki/pages?limit=3").Content
```

Expected:

```text
"items":[
```

and at least one `pageId`.

- [ ] **Step 3: Verify Vite proxy uses 8000**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run dev -- --host 127.0.0.1 --port 5173
```

Then in another shell:

```powershell
(Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5173/api/wiki/pages?limit=3").Content
```

Expected:

```text
same page data shape as 8000
```

- [ ] **Step 4: Verify 8001 is not required**

Run:

```powershell
netstat -ano | Select-String ":8001"
```

Expected:

```text
No LISTENING row for 8001
```

- [ ] **Step 5: Run backend and frontend tests**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python -m pytest tests/test_huiji_wiki_api.py tests/test_huiji_wiki_repository.py tests/test_huiji_wiki_e2e_script.py tests/test_wiki_mysql_migration_script.py -q

cd D:\PycharmProjects\nlp\LangChain\1999Search\frontend\react-app
npm run test -- --run src/api/wiki.test.ts src/App.wiki.test.tsx src/components/wiki
npm run build
```

Expected:

```text
all selected tests pass
Vite build succeeds
```

- [ ] **Step 6: Run read-only Wiki E2E**

Run:

```powershell
cd D:\PycharmProjects\nlp\LangChain\1999Search
python scripts/verify_huiji_wiki_e2e.py --base-url http://127.0.0.1:8000 --check-media --media-sample-limit 200 --media-assets data/processed/huiji/dev/media_assets.jsonl --inspection-label wiki-native-8000 --print-json-summary
```

Expected:

```text
local path leak count: 0
http media url count: greater than 0
"ok": true
```

- [ ] **Step 7: Run RAG smoke verification**

Run the RAG-approved smoke command:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ask" -ContentType "application/json" -Body '{"question":"介绍一下十四行诗","category":null}'
```

Expected:

```text
HTTP 200 with answer payload, or RAG-approved non-200 diagnostic if model credentials are intentionally unavailable.
```

If this step fails unexpectedly after MySQL switch, rollback `.env` to old MySQL settings and restart 8000.

## 5. Rollback Procedure

If Wiki or RAG verification fails after switching to project MySQL:

1. Restore `.env` values:

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=reverse1999_wiki
MYSQL_USER=root
MYSQL_PASSWORD=123456
```

2. Restart 8000.
3. Verify:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/wiki/pages?limit=3"
```

4. Keep `reverse1999-main-mysql` running for inspection; do not delete it during failure analysis.

## 6. Completion Checklist

- [ ] `NATIVE-P0-01` to `NATIVE-P0-07`: Wiki is native on 8000, has independent health, and startup delay is measured.
- [ ] `PROXY-P0-01` to `PROXY-P0-03`: Vite no longer defaults Wiki to 8001.
- [ ] `MYSQL-P0-01` to `MYSQL-P0-08`: Wiki MySQL migrated by dump/restore with matching row counts, no source password default, and rollback source retained.
- [ ] `MEDIA-RAG-P0-01` to `MEDIA-RAG-P0-04`: MinIO and media contract remain read-only and RAG-owned.
- [ ] `VERIFY-NATIVE-P0-01` to `VERIFY-NATIVE-P0-08`: Real 8000, real MySQL, real `/wiki`, startup timeout, and RAG smoke checks are recorded.
