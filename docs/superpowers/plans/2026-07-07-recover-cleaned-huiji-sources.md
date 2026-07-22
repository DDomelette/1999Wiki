# Recover Cleaned Huiji Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the untracked 1999Search huiji/wiki/RAG source files deleted during cleanup, while keeping Docker/database volumes and large model weights out of Git tracking.

**Architecture:** Prefer exact source recovery from IDE/local history or existing workspace copies. Fall back to Python bytecode decompilation only for missing Python modules. Rebuild TypeScript files only when no exact recovery source exists.

**Tech Stack:** Python 3.12, FastAPI backend, React/Vite frontend, pytest, npm/Vitest.

## Global Constraints

- Do not delete local Docker/database volume data.
- Do not re-track Toumanfen model weights.
- Do not use `git reset --hard`.
- Preserve existing 1999Search RAG/QA work.
- Treat deleted untracked files as recovery targets, not cleanup targets.

---

### Task 1: Snapshot Current Recovery State

**Files:**
- Create: `LangChain/1999Search/recovery-status-before.txt`

**Interfaces:**
- Consumes: current Git state and filesystem state.
- Produces: recovery audit snapshot.

- [x] Capture `git status --short` and key missing paths.
- [x] Confirm Docker volumes and model weights still exist locally.

### Task 2: Locate Exact Source Copies

**Files:**
- Read only across workspace and IDE/cache history locations.

**Interfaces:**
- Consumes: deleted path list.
- Produces: candidate source locations for direct restore.

- [x] Search workspace for `huiji_rag`, `huiji_wiki`, `WikiShell.tsx`, `MessageActions.tsx`, `storyCovers.ts`.
- [x] Search JetBrains/PyCharm local history and project metadata if accessible.

### Task 3: Restore Python Modules

**Files:**
- Create/restore: `LangChain/1999Search/src/huiji_rag/*.py`
- Create/restore: `LangChain/1999Search/src/huiji_wiki/*.py`
- Create/restore: `LangChain/1999Search/backend/wiki.py`
- Create/restore: `LangChain/1999Search/backend/wiki_schemas.py`
- Create/restore: `LangChain/1999Search/src/assets/huiji_registry.py`

**Interfaces:**
- Produces: imports used by backend and RAG code.

- [x] Restore exact source copies when available.
- [x] If source copies are unavailable, decompile `.cpython-312.pyc` files and manually correct output.

### Task 4: Restore Frontend Modules

**Files:**
- Create/restore: `LangChain/1999Search/frontend/react-app/src/components/wiki/*`
- Create/restore: `LangChain/1999Search/frontend/react-app/src/api/wiki.ts`
- Create/restore: `LangChain/1999Search/frontend/react-app/src/types/wiki.ts`
- Create/restore: `LangChain/1999Search/frontend/react-app/src/components/chat/MessageActions.tsx`
- Create/restore: `LangChain/1999Search/frontend/react-app/src/components/chat/VoicePanel.tsx`
- Create/restore: `LangChain/1999Search/frontend/react-app/src/components/chat/VideoPanel.tsx`
- Create/restore: `LangChain/1999Search/frontend/react-app/src/media/storyCovers.ts`

**Interfaces:**
- Produces: TypeScript modules referenced by current React code.

- [x] Restore exact source copies when available.
- [x] If source copies are unavailable, rebuild minimal compatible modules from current call sites.

### Task 5: Verify Recovery

**Files:**
- Read only.

**Interfaces:**
- Consumes: restored source files.
- Produces: evidence that missing imports are resolved.

- [x] Run targeted import reference scan.
- [x] Run targeted Python tests for recovered imports.
- [x] Run frontend type/build verification if dependencies are available.
- [ ] Run full backend SSE suite. Blocked by local `torch` DLL initialization failure in the Anaconda environment.

### Task 6: Report Final State

**Files:**
- Read only.

**Interfaces:**
- Produces: concise recovery report and remaining risks.

- [x] Summarize restored paths.
- [x] Summarize verification results.
- [x] Summarize remaining Git cleanup decisions.
