# Thread C Fidelity Closure Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Keep the execution topology at two layers: D supervises one C CLI worker; C must not create subagents.

**Goal:** Close Thread C through small, strictly serial fidelity gates, with one reviewed checkpoint for Task 7+C8a and one independent commit for every later phase.

**Architecture:** C8a closes exclusion identity only. C8b and C8c are architecture-decision gates owned by D before C writes code. C8d runs a fixed, self-contained, read-only real-snapshot fidelity entry point, and C9 performs final regression and ownership audit. D alone merges to `main` and, only after merge, decides whether vector rebuilding is necessary.

**Tech Stack:** Python 3.11.15 from `D:\Anaconda32024\envs\1999wiki\python.exe`, pytest, Git worktrees, PowerShell, JSON/JSONL and SHA-256, existing Huiji corpus fidelity contracts.

## Global Constraints

- Worktree: `D:\1999Wiki.worktrees\rag-c-projection`.
- C uses model `gpt-5.6-sol`, standard speed, `fast_mode=false`, `multi_agent=false`.
- Every Python command uses `D:\Anaconda32024\envs\1999wiki\python.exe`; bare `python`, `py`, and another Conda environment are forbidden.
- C never downloads media, writes MinIO/MySQL/Milvus, rebuilds vectors, activates a candidate, changes an active pointer, or rewrites a production baseline.
- Real diagnostic output is create-new and ignored under `eval/task8-c-<run-id>/`.
- Evidence must not contain raw Wikitext, credentials, absolute-path samples, or an unbounded blocker list.
- D reviews tests, source diff, real-snapshot evidence, protected-state hashes, and file ownership before authorizing each commit.
- C8b, C8c, C8d, and C9 each start in a fresh CLI turn. C8b starts in a new CLI session after the Task 7+C8a checkpoint commit.
- A phase cannot edit files, tests, or policy owned by a later phase.

---

### Task 1: Complete C8a Exclusion Fidelity Closure

**Files:**

- Modify: `src/huiji_rag/build/wikitext_projection.py`
- Modify: `src/huiji_rag/build/projection.py`
- Modify: `src/huiji_rag/build/fidelity.py`
- Test: `tests/test_huiji_wikitext_projection.py`
- Test: `tests/test_huiji_corpus_projection.py`
- Test: `tests/test_huiji_corpus_fidelity.py`
- Evidence: new ignored `eval/task8-c-<run-id>/`

**Interfaces:**

- Consumes: `WikitextDiagnostic`, `PageDiagnostic`, `ProjectionExclusion`, `_exclusion_candidate_identity()`.
- Produces: source-backed exclusion identities stable across repeated projection and unique across distinct source occurrences.

- [ ] **Step 1: Preserve scanner occurrence evidence**

For every scanner diagnostic and `duplicate_heading_path_occurrence`, populate:

```python
PageDiagnostic(
    reason_code=reason_code,
    pageid=pageid,
    source_title=title,
    details=sanitized_details,
    revid=joined_revision.revid,
    source_content_sha256=source_content_sha256,
    char_start=source_occurrence.char_start,
    char_end=source_occurrence.char_end,
    heading_path=source_occurrence.heading_path,
)
```

Do not derive the range from list order and do not place raw source text in `details`.

- [ ] **Step 2: Verify RED before implementation**

Run the smallest tests that assert:

```text
two same-reason diagnostics at different ranges have distinct identities
repeated projection produces identical identities
duplicate-heading diagnostics retain revision/hash/range/heading evidence
an exact duplicate payload deduplicates deterministically
the same identity with conflicting payload fails closed
```

Expected before the final fix: the duplicate-heading evidence test fails because the diagnostic uses page-level fallback identity.

- [ ] **Step 3: Verify GREEN and the five-file regression**

Run:

```powershell
& 'D:\Anaconda32024\envs\1999wiki\python.exe' -m pytest `
  tests/test_huiji_wikitext_projection.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_huiji_corpus_fidelity.py `
  tests/test_huiji_corpus_builder.py `
  tests/test_huiji_corpus_artifacts.py -q `
  --basetemp .pytest-c8a-final
```

Expected: all tests pass; the current accepted floor is 76 tests.

- [ ] **Step 4: Run one real-snapshot exclusion diagnostic**

The run must prove:

```text
fidelity function returns instead of raising an exclusion identity error
duplicate exclusion ledger group count == 0
exact duplicate payloads use one deterministic ledger identity
conflicting payloads still fail closed in tests
protected identity count == 32
protected drift count == 0
```

The diagnostic may report later Story or media blockers; those do not fail C8a.

- [ ] **Step 5: D independently reviews the checkpoint**

D runs:

```powershell
git diff --check
git diff --name-only
git status --short
```

D also reruns the five-file regression with a new `--basetemp`, validates evidence JSON and SHA-256, checks the protected pre/post hashes, and confirms no external writes.

- [ ] **Step 6: Create one Task 7+C8a checkpoint commit**

Do not attempt a risky historical hunk split because Task 7 and C8a overlap. After D approval, commit the accepted Task 7 integration plus C8a closure:

```powershell
git add -- `
  src/huiji_rag/build `
  src/huijiwiki/resource_downloader.py `
  tests/test_huiji_corpus_artifacts.py `
  tests/test_huiji_corpus_builder.py `
  tests/test_huiji_corpus_builder_contracts.py `
  tests/test_huiji_corpus_fidelity.py `
  tests/test_huiji_corpus_projection.py `
  tests/test_huiji_media_download_plan.py `
  tests/test_huiji_resource_downloader.py `
  tests/test_huiji_topic_projection.py `
  tests/test_huiji_wikitext_projection.py
git commit -m "feat(rag): integrate corpus builder and close exclusion fidelity"
```

Ignored real-snapshot evidence, pytest basetemps, raw files, processed artifacts, and permission-warning review directories must not be staged.

---

### Task 2: Start a Fresh C Session With a Machine-Readable Handoff

**Files:**

- Create: `.codex-supervisor/workers/C/handoff-c8b.json`
- Modify only if needed for truthful state: `src/codex_supervisor/`
- Test only if supervisor code changes: `tests/test_codex_supervisor_cli.py`

**Interfaces:**

- Consumes: Task 7+C8a checkpoint commit SHA and the latest fidelity blocker-prefix counts.
- Produces: a short handoff used to start a new C CLI session in the same worktree.

- [ ] **Step 1: Write the handoff**

Use this exact schema:

```json
{
  "schema_version": "codex.thread-c-handoff/v1",
  "checkpoint_commit": "<40-hex commit>",
  "worktree": "D:\\1999Wiki.worktrees\\rag-c-projection",
  "next_phase": "C8b",
  "remaining_blocker_prefix_counts": {},
  "protected_identity_count": 32,
  "protected_drift_count": 0,
  "forbidden_actions": [
    "media_download",
    "vector_rebuild",
    "activation",
    "production_write",
    "subagent"
  ]
}
```

The blocker counts must come from the accepted C8a real diagnostic, not be copied from an older run.

- [ ] **Step 2: Close the old CLI runner**

Require the old runner and its child process to exit. Confirm with OS process inspection; `status=running` with `pid=null` is not sufficient evidence.

- [ ] **Step 3: Start a new C CLI session**

Start the new session in the existing C worktree, pinned to the checkpoint commit and C8b decision-only prompt.

- [ ] **Step 4: Record truthful supervision metadata**

For every run, D records:

```text
run_id
runner_pid
worker_process_pid
last_heartbeat_utc
last_output_utc
current_evidence_directory
```

Until the supervisor persists these fields reliably, D must verify both OS process state and output/evidence timestamps. A nullable PID alone never establishes liveness.

---

### Task 3: Freeze C8b Story and Legacy Parent/Child Migration Rules

**Files:**

- Create: `docs/superpowers/specs/2026-07-29-rag-thread-c-story-migration-decision.md`
- Evidence: new ignored `eval/task8-c-<run-id>/story-migration-taxonomy.v1.json`
- No production code changes in the decision turn.

**Interfaces:**

- Consumes: accepted C8a checkpoint, current active Parent/Child rows, candidate Parent/Child rows, `SemanticRecordLink`.
- Produces: a D-approved classification rule for every candidate Story record and every legacy missing Parent/Child pair.

- [ ] **Step 1: Generate a read-only migration taxonomy**

Report dynamic counts and sanitized samples for:

```text
candidate Story parents without record links
candidate Story children without record links
legacy Parent rows missing in candidate
legacy Child rows missing in candidate
exact stable-source matches
owner-preserving rekeys
content-equivalent rekeys
source-removed candidates with source evidence
ambiguous or conflicting matches
```

Do not hardcode `2,222`; report the value computed from the accepted snapshot.

- [ ] **Step 2: D writes the migration decision**

For each discovered class, D chooses exactly one allowed fidelity outcome:

```text
new_source_record
rekeyed
corrected_with_evidence
source_removed_with_evidence
blocked_ambiguous
```

The decision must state the matching keys, required source evidence, owner constraints, and fail-closed condition. “New and old coexist” is allowed only when the rows represent distinct source facts and both retain independent stable identities.

- [ ] **Step 3: Obtain approval before implementation**

C must not infer or broaden the migration rule. D presents the decision for approval, then places the approved decision file and its SHA-256 in the C8b resume prompt.

- [ ] **Step 4: Implement C8b test-first**

Allowed production files are frozen by the approved decision. Tests must compute classification counts from fixtures and prove ambiguous matches remain blockers.

- [ ] **Step 5: Verify and commit C8b independently**

Run the approved focused suite and a real-snapshot Parent/Child fidelity diagnostic. After D review:

```powershell
git commit -m "feat(rag): classify story and legacy corpus migration"
```

The commit contains C8b only.

---

### Task 4: Freeze C8c Legacy Media-Binding Classification

**Files:**

- Create: `docs/superpowers/specs/2026-07-29-rag-thread-c-legacy-media-decision.md`
- Evidence: new ignored `eval/task8-c-<run-id>/legacy-media-taxonomy.v1.json`
- No production code changes in the decision turn.

**Interfaces:**

- Consumes: accepted C8b commit, active media bindings, candidate media intents/assets, resource manifest metadata, local-byte verification state.
- Produces: a D-approved classification for every legacy media occurrence.

- [ ] **Step 1: Generate a read-only occurrence taxonomy**

For every active occurrence, classify by evidence into:

```text
preserved_binding
rekeyed_binding
source_removed_with_evidence
missing_local_bytes
missing_resource_metadata
ambiguous_binding
conflicting_binding
```

Report the real count computed from the snapshot rather than hardcoding `15,758`.

- [ ] **Step 2: Keep insufficient evidence blocked**

`missing_local_bytes`, `missing_resource_metadata`, `ambiguous_binding`, and `conflicting_binding` cannot be silently counted as preserved or removed. No filename similarity, ordinal, or count-only reconciliation is sufficient evidence.

- [ ] **Step 3: D writes and approves the media decision**

The decision defines exact resource identity, binding identity, owner/child constraints, and the evidence required for rekey or source removal. This phase does not approve downloads.

- [ ] **Step 4: Implement C8c test-first**

Tests prove each approved class and prove insufficient evidence remains an explicit blocker.

- [ ] **Step 5: Verify and commit C8c independently**

Run focused media/fidelity tests and a real-snapshot media reconciliation diagnostic. After D review:

```powershell
git commit -m "feat(rag): classify legacy media binding fidelity"
```

The commit contains C8c only and downloads no media.

---

### Task 5: Run C8d With a Self-Contained Diagnostic Entry Point

**Files:**

- Create or modify: one reviewed read-only diagnostic entry point under `scripts/` or `src/huiji_rag/build/`
- Test: one focused test proving offline/no-write behavior
- Evidence: new ignored `eval/task8-c-<run-id>/`

**Interfaces:**

- Consumes: accepted C8a, C8b, and C8c commits plus the frozen source snapshot.
- Produces: immutable full fidelity evidence and remaining blocker-prefix counts.

- [ ] **Step 1: Freeze the diagnostic identity**

Record:

```text
diagnostic script relative path
diagnostic script SHA-256
git commit SHA
input snapshot file names/sizes/SHA-256/row counts
run_id
expected output file names
protected identity manifest SHA-256
```

The entry point must be self-contained in the checked-out commit. A new run script must not `exec()` or import an older ignored run directory.

- [ ] **Step 2: Prove offline/no-write behavior**

The focused test blocks network and production writers and asserts the diagnostic creates files only under its new output root.

- [ ] **Step 3: Run the full real snapshot**

Require the fidelity function to return normally. Write only summarized blocker-prefix counts and bounded sanitized samples.

- [ ] **Step 4: Verify immutable evidence**

Require:

```text
script SHA matches frozen identity
input snapshot identities match
all expected outputs exist
protected pre/post count == 32
protected drift count == 0
network/download/media-byte/vector/activation/production writes == 0
```

- [ ] **Step 5: Commit C8d independently**

Commit only the reusable diagnostic entry point and its tests. Do not commit real run outputs:

```powershell
git commit -m "test(rag): add self-contained corpus fidelity diagnostic"
```

---

### Task 6: Run C9 Final Regression and Scope Audit

**Files:**

- No production edits unless a test reveals a separately approved defect.
- Evidence: test logs and a final ignored audit summary.

**Interfaces:**

- Consumes: accepted C8d commit and immutable diagnostic evidence.
- Produces: merge-ready C branch handoff.

- [ ] **Step 1: Run all Thread C focused tests**

Run the complete focused list from the original Thread C plan with the exact Conda interpreter and a fresh basetemp.

- [ ] **Step 2: Run adjacent projection, media, Voice, provenance, and builder regressions**

Expected: all pass. Any failure starts a new bounded correction gate; it is not folded silently into C9.

- [ ] **Step 3: Verify deterministic fixture closure**

Build the small four-source fixture twice in new temporary roots and compare ordered semantic bytes, IDs, fingerprints, exclusions, and media-binding identities.

- [ ] **Step 4: Audit ownership and diff**

Run:

```powershell
git diff --check
git status --short
git diff --name-only
git log --oneline --decorate -10
```

Confirm no A/B runtime files, raw snapshots, ignored diagnostics, pytest basetemps, active pointers, credentials, or production artifacts are tracked.

- [ ] **Step 5: Produce the D handoff**

The handoff includes commit SHAs for Task 7+C8a, C8b, C8c, and C8d; test commands and counts; immutable C8d evidence identities; remaining explicit blockers; and whether text artifacts changed in a way that may require vector rebuilding.

---

### Task 7: D Validates and Merges to Main

**Files:**

- Main worktree only.
- No vector or production mutation during merge validation.

**Interfaces:**

- Consumes: C9 merge-ready handoff.
- Produces: validated merge commit on `main`.

- [ ] **Step 1: Review every phase commit**

D checks each commit against its allowlist and decision receipt.

- [ ] **Step 2: Merge without discarding unrelated main changes**

Preserve all user-owned dirty files. Resolve only conflicts caused by accepted A, B, and C changes.

- [ ] **Step 3: Run post-merge verification**

Run the combined focused and adjacent suites in Conda `1999wiki`.

- [ ] **Step 4: Decide vector rebuilding after merge**

Only D may rebuild vectors. Rebuild only if the merged canonical text corpus, child identities, embedding inputs, or active vector schema require it. Analyzer-only BM25 changes do not by themselves authorize a vector rebuild.

- [ ] **Step 5: Keep activation separately gated**

A successful vector rebuild does not automatically authorize production activation, pointer changes, or service writes.
