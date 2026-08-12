# 1999Search Bilingual README and RAG Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current project overview with equivalent Chinese and English GitHub READMEs that help open-source users deploy, understand, troubleshoot, and extend 1999Search, with special emphasis on its trustworthy RAG pipeline.

**Architecture:** `README.md` remains the Simplified Chinese GitHub entry point and `README_EN.md` becomes the complete English counterpart. Both files use the same section order, Mermaid topology, commands, paths, configuration keys, and public API facts; volatile operational detail stays linked to the existing runbooks.

**Tech Stack:** GitHub-flavored Markdown, Mermaid, FastAPI, React/Vite, Milvus, BGE-M3, MySQL, MinIO, PowerShell, pytest

## Global Constraints

- The primary audience is open-source users deploying or extending the project.
- `README.md` is the complete Simplified Chinese edition; `README_EN.md` is the complete English edition; each links to the other at the top.
- Current facts come from code, `config/settings.yaml`, the provenance baseline, checked-in examples, and tests—not from historical design intent.
- Preserve the distinction between the offline corpus/index pipeline and the online query/citation pipeline in two dedicated Mermaid diagrams.
- Explain that Huiji crawler is the formal corpus source and retired pipelines are not rollback paths.
- Explain the runtime fail-closed contract: it does not rebuild or activate indexes; artifact, BM25, collection, or provenance mismatch leaves health endpoints available and RAG unavailable.
- Explain that current SSE output is emitted only after complete generation and citation validation; do not describe it as native model token streaming.
- Describe the reranker as optional and disabled by default.
- Do not claim a fresh production full-chain evaluation or advertise an online demo.
- Do not invent a license. If no `LICENSE*` file exists, state that reuse terms have not yet been published.
- Do not expose credentials, local secret values, private filesystem paths, or external-service responses.
- Do not modify application behavior, rebuild/activate/delete Milvus collections, call paid model services, deploy, or change unrelated dirty-worktree files.

## File Structure

- Modify: `README.md` — complete Simplified Chinese project entry point.
- Create: `README_EN.md` — structurally equivalent complete English project entry point.
- Reference only: `docs/architecture.md`, `docs/huiji-rag-runbook.md`, `docs/project-understanding/rag-qa-chain-analysis.md`, `docs/rag-assets.md` — deeper architecture and operations links.
- Reference only: `backend/main.py`, `backend/schemas.py`, `backend/wiki.py`, `src/rag/`, `src/huiji_rag/`, `src/assets/`, `config/settings.yaml`, `deploy/env/*.example` — sources of truth for documentation claims.

---

### Task 1: Rewrite the Simplified Chinese GitHub entry point

**Files:**
- Modify: `README.md`
- Reference: `backend/main.py`
- Reference: `backend/schemas.py`
- Reference: `backend/wiki.py`
- Reference: `config/settings.yaml`
- Reference: `deploy/env/app.env.example`

**Interfaces:**
- Consumes: approved design in `docs/superpowers/specs/2026-08-12-github-readme-rag-presentation-design.md` and the current public/configuration contracts.
- Produces: the canonical section order, Mermaid topology, commands, tables, links, and terminology that `README_EN.md` must mirror.

- [ ] **Step 1: Capture the current public and runtime facts before editing**

Run:

```powershell
rg -n '@(app|router)\.(get|post|delete)\(' backend
rg -n 'class (AskRequest|AskResponse|SourceItem|HealthResponse)|grounding_mode|coverage_shortfall|conversation_id' backend\schemas.py
Get-Content -Raw -Encoding UTF8 config\settings.yaml
Get-Content -Raw -Encoding UTF8 deploy\env\app.env.example
Get-ChildItem -Name LICENSE*
```

Expected: routes include `/health/live`, `/health/ready`, `/health`, `/ask`, `/ask/stream`, `/conversations/{conversation_id}`, `/api/media/voice/page`, and `/api/wiki/*`; configuration confirms Huiji crawler, Milvus, BGE-M3, optional disabled reranking, MinIO, and MySQL; no license file is currently listed.

- [ ] **Step 2: Replace the current README with the approved GitHub information architecture**

Write these sections in this exact order:

```text
Language switch
Title and one-sentence positioning
Capability summary and page links
Project overview / screenshots only if tracked assets are suitable
System architecture Mermaid diagram
Technology and component responsibility table
Offline corpus and index Mermaid diagram
Online trustworthy RAG Mermaid diagram
RAG design details and trust boundaries
Prerequisites
Quick start
Configuration
Service endpoints and API examples
Data/index maintenance
Secondary-development map
Testing
Troubleshooting
Repository structure
Deep documentation
Data source, unofficial-project notice, and license status
```

Use relative repository links, PowerShell commands for the primary local path, and shell/Compose commands only where checked-in production scripts support them. Refer to the active collection through `huiji.text_collection_name` and provenance instead of duplicating a volatile dated name in the status banner.

- [ ] **Step 3: Verify every Chinese claim against its source of truth**

Run:

```powershell
rg -n 'Huiji|huiji_crawler|BGE-M3|Milvus|BM25|RRF|owner|S01|provenance|shadow|SSE|ResponsePacket|reranker|503|LICENSE' README.md
rg -n 'text_child_bge_m3_shadow_crawler_v3_20260721t051246z|source_mode|reranker|backend_port|streamlit_port|gradio_port' config\settings.yaml deploy\env\app.env.example
```

Expected: README contains every trust-boundary concept; any literal collection example agrees with current config; the reranker is not described as enabled.

- [ ] **Step 4: Check the Chinese README diff and commit the canonical edition**

Run:

```powershell
git diff --check -- README.md
git diff -- README.md
git status --short
git add -- README.md
git commit -m "docs: expand Chinese README and RAG architecture"
```

Expected: only `README.md` is staged for this commit; unrelated pre-existing worktree changes remain unstaged.

### Task 2: Create the complete English counterpart

**Files:**
- Create: `README_EN.md`
- Reference: `README.md`

**Interfaces:**
- Consumes: the canonical headings, diagrams, commands, paths, tables, and terminology from Task 1.
- Produces: a complete English README with the same operational meaning and GitHub navigation.

- [ ] **Step 1: Create the English edition section-for-section**

Translate explanatory prose while preserving these items byte-for-byte wherever practical:

```text
Mermaid node topology and edge direction
commands and request bodies
paths, route names, ports, configuration keys, model identifiers
table row order
warning scope and trust-boundary meaning
```

The first line must link back to `README.md`; the Chinese README must link to `README_EN.md`.

- [ ] **Step 2: Compare bilingual document structure**

Run:

```powershell
$cn = Get-Content -Encoding UTF8 README.md
$en = Get-Content -Encoding UTF8 README_EN.md
$cnHeadings = @($cn | Where-Object { $_ -match '^#{1,6} ' })
$enHeadings = @($en | Where-Object { $_ -match '^#{1,6} ' })
$cnMermaid = @($cn | Where-Object { $_ -eq '```mermaid' }).Count
$enMermaid = @($en | Where-Object { $_ -eq '```mermaid' }).Count
$cnFences = @($cn | Where-Object { $_ -match '^```' }).Count
$enFences = @($en | Where-Object { $_ -match '^```' }).Count
[pscustomobject]@{ CNHeadings=$cnHeadings.Count; ENHeadings=$enHeadings.Count; CNMermaid=$cnMermaid; ENMermaid=$enMermaid; CNFences=$cnFences; ENFences=$enFences }
if ($cnHeadings.Count -ne $enHeadings.Count -or $cnMermaid -ne $enMermaid -or $cnFences -ne $enFences) { exit 1 }
```

Expected: equal heading, Mermaid block, and fenced-code-block counts.

- [ ] **Step 3: Compare stable commands and technical identifiers**

Run:

```powershell
$terms = @('/health','/ask','/ask/stream','/api/media/voice/page','/api/wiki','start.ps1','start.bat','config/settings.yaml','src/rag/','src/huiji_rag/','BAAI/bge-m3','deepseek-v4-flash','S01','ResponsePacket')
foreach ($term in $terms) {
  if (-not (Select-String -Path README.md -SimpleMatch $term -Quiet)) { Write-Error "Chinese README missing $term"; exit 1 }
  if (-not (Select-String -Path README_EN.md -SimpleMatch $term -Quiet)) { Write-Error "English README missing $term"; exit 1 }
}
```

Expected: every stable identifier appears in both editions.

- [ ] **Step 4: Check and commit the English edition**

Run:

```powershell
git diff --check -- README.md README_EN.md
git diff -- README.md README_EN.md
git status --short
git add -- README.md README_EN.md
git commit -m "docs: add complete English README"
```

Expected: the second commit contains `README_EN.md` and only a language-link correction in `README.md` if Task 1 did not already include it.

### Task 3: Validate GitHub rendering, links, examples, and focused contracts

**Files:**
- Verify: `README.md`
- Verify: `README_EN.md`
- Amend only if validation finds a documentation defect.

**Interfaces:**
- Consumes: both README editions from Tasks 1 and 2.
- Produces: fresh evidence that formatting, links, diagrams, public routes, and bilingual parity satisfy the design.

- [ ] **Step 1: Validate repository-relative links**

Run:

```powershell
$failed = @()
foreach ($file in @('README.md','README_EN.md')) {
  $text = Get-Content -Raw -Encoding UTF8 $file
  foreach ($match in [regex]::Matches($text, '\[[^\]]+\]\(([^)]+)\)')) {
    $target = $match.Groups[1].Value
    if ($target -match '^(https?://|#)') { continue }
    $path = [uri]::UnescapeDataString(($target -split '#',2)[0])
    if ($path -and -not (Test-Path (Join-Path (Split-Path $file) $path))) { $failed += "$file -> $target" }
  }
}
if ($failed.Count) { $failed; exit 1 }
```

Expected: exit 0 with no missing targets.

- [ ] **Step 2: Extract Mermaid blocks and run a structural syntax check**

Run:

```powershell
foreach ($file in @('README.md','README_EN.md')) {
  $inside = $false; $blocks = 0; $hasDirection = $false
  foreach ($line in Get-Content -Encoding UTF8 $file) {
    if ($line -eq '```mermaid') { if ($inside) { exit 1 }; $inside=$true; $blocks++; continue }
    if ($inside -and $line -eq '```') { $inside=$false; continue }
    if ($inside -and $line -match '^\s*(flowchart|graph)\s+(TB|TD|BT|RL|LR)') { $hasDirection=$true }
  }
  if ($inside -or $blocks -lt 3 -or -not $hasDirection) { Write-Error "$file Mermaid structure invalid"; exit 1 }
}
```

Expected: each README has at least the system, offline, and online diagrams; all fences close and a supported graph direction is declared. If Mermaid CLI is already available, additionally render every extracted block; do not install new global tooling for this task.

- [ ] **Step 3: Verify the referenced API and RAG contracts with focused tests**

Run:

```powershell
python -m pytest tests\test_config.py tests\test_conversation_api.py tests\test_rag_contracts.py tests\test_citations.py tests\test_sse.py -q
```

Expected: exit 0 and no failed tests. These tests cover configuration, public ask/conversation schemas, immutable response contracts, citation behavior, and SSE transport semantics referenced by the README.

- [ ] **Step 4: Run final bilingual and worktree checks**

Run:

```powershell
git diff --check HEAD~2..HEAD -- README.md README_EN.md
git log -2 --oneline -- README.md README_EN.md
git status --short
```

Expected: no whitespace errors; the two documentation commits are visible; all unrelated pre-existing changes remain present and were not included in either README commit.

- [ ] **Step 5: Correct validation defects and record the correction if needed**

If Steps 1–4 identify a README-only defect, edit only `README.md` and/or `README_EN.md`, rerun all four validation steps, then run:

```powershell
git add -- README.md README_EN.md
git commit -m "docs: correct bilingual README validation issues"
```

Expected: no correction commit is created when validation is already clean; otherwise the commit contains only the verified README fixes.
