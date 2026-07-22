# Huiji RAG 唯一数据源收口 P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user has explicitly selected inline execution without subagents.

**Goal:** 将当前正确运行的 Huiji RAG 状态固化为可审计、启动前 fail-closed、旧入口不可误写、且只能向显式非活动 shadow collection 重建的 P0 契约。

**Architecture:** 新增纯只读 provenance 核心库，离线深度审计负责证明 crawler raw 到 artifacts、BM25 和活动 Milvus 的完整来源关系，快速 verifier 只核对 hash-pinned baseline、当前 artifacts、配置和活动 Milvus。Launcher 与 FastAPI 共用该 verifier；Huiji builder 只允许创建不存在的非活动 collection，并在成功或失败时写入唯一、hash-pinned evidence。

**Tech Stack:** Python 3、dataclasses、Pydantic/FastAPI、pytest、PyYAML、pymilvus/MilvusClient、现有 Huiji JSONL/BM25 artifacts、PowerShell、Windows Batch。

**Approved spec:** `docs/superpowers/specs/2026-07-18-huiji-rag-source-of-truth-hardening-design.md`

## Global Constraints

- 本计划只实现 `SOURCE-GATE-P0-01..05`、`RUNTIME-GATE-P0-01..06`、`LEGACY-BLOCK-P0-01..03`、`SHADOW-BUILD-P0-01..07`；P1/P2 不进入任何执行任务。
- 生产 source mode 固定为 `huiji_crawler`，活动 build 固定由配置与 baseline 共同决定，不把当前观察到的 16,010 行写成代码常量。
- P0 不删除旧文件、MinIO 对象、MySQL supplements、Milvus collection 或历史文档。
- 实施期间活动 Milvus、MinIO、MySQL 和正式 artifacts 只读；唯一批准的业务基础设施写入是创建一个新命名的非活动 Milvus shadow collection。
- 所有 baseline、audit、runtime、shadow 和 acceptance evidence 使用 canonical JSON、SHA-256 sidecar、create-new 语义；不得覆盖已有 evidence。
- evidence、健康响应和错误信息不得包含本地绝对路径、凭据、source content、问题正文或回答正文。
- provenance 失败、验证器异常、活动 collection 名冲突、目标已存在或 protected snapshot 漂移都必须 fail closed。
- shadow 构建失败时保留失败 collection 和 evidence，不自动删除，不用同名重试。
- 执行直接在当前脏工作树进行；按用户要求不创建 worktree、不提交或整理 Git。

---

## 1. Scope And Requirement Map

| P0 requirement | Implementation task | Unit/integration gate | Real gate |
|---|---:|---|---|
| `SOURCE-GATE-P0-01` | 3, 4 | config/source-mode mismatch tests | installed baseline + runtime pass |
| `SOURCE-GATE-P0-02` | 1, 2, 3 | artifact/BM25/Milvus fingerprint tests | deep audit candidate baseline |
| `SOURCE-GATE-P0-03` | 3 | runtime cannot write baseline test | baseline install from passed audit only |
| `SOURCE-GATE-P0-04` | 3 | source/media missing and hash mismatch tests | full crawler reverse-reference audit |
| `SOURCE-GATE-P0-05` | 1, 3, 5 | sanitizer and response leakage tests | final evidence leakage scan |
| `RUNTIME-GATE-P0-01` | 4, 5, 6 | CLI/backend/launcher tests | launcher and direct uvicorn smoke |
| `RUNTIME-GATE-P0-02` | 2, 4, 5 | artifact and Milvus drift tests | controlled temporary-copy mismatch |
| `RUNTIME-GATE-P0-03` | 4, 5 | verifier exception test | unavailable fake collection gate |
| `RUNTIME-GATE-P0-04` | 5 | health/ask/stream/media API tests | blocked backend smoke |
| `RUNTIME-GATE-P0-05` | 4 | raw-root access spy test | runtime evidence timing/input list |
| `RUNTIME-GATE-P0-06` | 1, 2, 4 | mutation methods raise if called | pre/post protected snapshot equality |
| `LEGACY-BLOCK-P0-01` | 7 | old CLI mutation spies remain zero | invoke all three commands |
| `LEGACY-BLOCK-P0-02` | 6 | launcher text/order tests | launcher gate smoke |
| `LEGACY-BLOCK-P0-03` | 6, 7 | no bypass/fallback assertion | residue inventory remains present |
| `SHADOW-BUILD-P0-01` | 8 | required CLI argument test | missing target rejected |
| `SHADOW-BUILD-P0-02` | 8 | active-name call-order tests | configured/baseline active names rejected |
| `SHADOW-BUILD-P0-03` | 8 | existing-target call-order tests | retained shadow name rejected on rerun |
| `SHADOW-BUILD-P0-04` | 8 | provenance-before-embedding tests | drifted input rejected before build |
| `SHADOW-BUILD-P0-05` | 2, 8 | schema/row/ID/content mismatch tests | full real shadow comparison |
| `SHADOW-BUILD-P0-06` | 8, 10 | settings hash unchanged test | pre/post protected snapshot equality |
| `SHADOW-BUILD-P0-07` | 1, 8, 10 | pass/fail evidence tests | retained shadow + final evidence |

## 2. File Structure

### Create

- `src/huiji_rag/provenance.py`: canonical serialization, artifact/BM25/Milvus fingerprints, deep audit, baseline model, runtime verifier, sanitizer and hash-pinned evidence writer.
- `scripts/audit_huiji_provenance.py`: `audit` and `install-baseline` CLI; only this deep-audit path may produce a baseline candidate.
- `scripts/verify_huiji_runtime.py`: fast verifier CLI used by launchers and operators.
- `scripts/build_huiji_index.py`: explicit non-active shadow builder CLI.
- `scripts/verify_huiji_provenance_acceptance.py`: protected snapshot capture/compare and dynamic active-source sampling.
- `tests/test_huiji_provenance.py`: canonicalization, artifact/BM25, source/media audit, baseline and runtime tests.
- `tests/test_huiji_shadow_builder.py`: shadow safety, call ordering, verification and evidence tests.
- `tests/test_backend_provenance_gate.py`: backend pass/blocked/error and API contract tests.
- `tests/test_legacy_rag_cli_blocked.py`: tombstone call-order tests.
- `tests/test_huiji_source_docs.py`: current-source and runbook safety assertions.
- `config/provenance/huiji-dev.v1.json`: generated only after the real deep audit passes and the candidate is reviewed.

### Modify

- `config/config.py`: add `HuijiCfg.source_mode` and `HuijiCfg.provenance_baseline`.
- `config/settings.yaml`: pin `source_mode: huiji_crawler` and the relative baseline path.
- `src/rag/vectorstore.py`: expose one canonical non-vector business projection and replace the Huiji write helper with create-new shadow semantics.
- `backend/schemas.py`: add safe provenance fields to `/health`.
- `backend/main.py`: run and cache provenance before loading vectorstore/Retriever/RAGChain.
- `start.ps1`, `start.bat`: remove legacy auto-build and run verifier before backend startup.
- `scripts/extract_data.py`, `scripts/build_index.py`, `scripts/build_assets.py`: fail-closed tombstones.
- `tests/test_config.py`, `tests/test_vectorstore.py`, `tests/test_start_scripts.py`: extend existing contracts.
- `README.md`: add a current Huiji-only status banner and mark legacy sections historical.
- `docs/architecture.md`: replace the current data-flow header with Huiji provenance flow and mark Obsidian flow historical.
- `docs/huiji-rag-runbook.md`: replace unsafe builder/switch/rollback commands with audit, runtime verify and shadow-only commands.

---

### Task 1: Canonical Provenance And Artifact Fingerprints

**Corresponding specs:** `SOURCE-GATE-P0-02`, `SOURCE-GATE-P0-05`, `RUNTIME-GATE-P0-05`, `RUNTIME-GATE-P0-06`, `SHADOW-BUILD-P0-07`

**Files:**
- Create: `src/huiji_rag/provenance.py`
- Create: `tests/test_huiji_provenance.py`

**Interfaces:**
- Produces: `ArtifactFingerprint`, `Bm25Fingerprint`, `VerificationIssue`, `VerificationResult`, `canonical_json_bytes()`, `sha256_file()`, `fingerprint_jsonl()`, `fingerprint_bm25()`, `write_hash_pinned_json()`, `safe_relative_path()`.
- Consumes: existing UTF-8 JSONL and BM25 `{ "records": [...] }` files.
- Mutation boundary: this task may only create caller-selected evidence files; it does not import or initialize Milvus, MinIO or MySQL clients.

- [ ] **Step 1: Write failing canonicalization, path containment and create-new evidence tests**

```python
def test_canonical_json_and_hash_pinned_evidence_are_stable_and_create_new(tmp_path):
    target = tmp_path / "evidence.v1.json"
    payload = {"z": 1, "a": ["文本", 2]}
    digest = write_hash_pinned_json(target, payload)
    assert target.read_bytes() == b'{"a":["\xe6\x96\x87\xe6\x9c\xac",2],"z":1}\n'
    assert (tmp_path / "evidence.v1.json.sha256").read_text(encoding="ascii") == (
        f"{digest}  evidence.v1.json\n"
    )
    with pytest.raises(FileExistsError):
        write_hash_pinned_json(target, payload)


def test_safe_relative_path_rejects_escape_and_absolute_path(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    assert safe_relative_path(root / "data" / "x.jsonl", root) == "data/x.jsonl"
    with pytest.raises(ValueError, match="outside project root"):
        safe_relative_path(tmp_path / "outside.jsonl", root)
```

- [ ] **Step 2: Run the focused tests and confirm the module is absent**

Run: `conda run -n langchain python -m pytest tests/test_huiji_provenance.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'src.huiji_rag.provenance'`.

- [ ] **Step 3: Define stable models, error ordering and evidence primitives**

Implement these exact public models and constants:

```python
BASELINE_SCHEMA = "huiji.provenance_baseline/v1"
AUDIT_SCHEMA = "huiji.provenance_audit/v1"
RUNTIME_SCHEMA = "huiji.runtime_verification/v1"
SOURCE_MODE = "huiji_crawler"

class ProvenanceValidationError(ValueError):
    def __init__(self, code: str, component: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.component = component

@dataclass(frozen=True)
class ArtifactFingerprint:
    relative_path: str
    sha256: str
    size_bytes: int
    row_count: int
    id_field: str
    id_count: int
    unique_id_count: int
    ids_sha256: str
    semantic_sha256: str

@dataclass(frozen=True)
class Bm25Fingerprint:
    relative_path: str
    sha256: str
    size_bytes: int
    row_count: int
    ids_sha256: str
    semantic_sha256: str

@dataclass(frozen=True, order=True)
class VerificationIssue:
    code: str
    component: str
    expected: str = ""
    actual: str = ""

@dataclass(frozen=True)
class VerificationResult:
    status: Literal["pass", "blocked", "error"]
    issues: tuple[VerificationIssue, ...]
    baseline_sha256: str
    evidence_relpath: str = ""
    duration_ms: int = 0

    @property
    def allowed(self) -> bool:
        return self.status == "pass" and not self.issues
```

`canonical_json_bytes()` must use `ensure_ascii=False`, `sort_keys=True`, compact separators and one trailing LF. `write_hash_pinned_json()` creates the parent directory, then opens both JSON and sidecar with `xb`; if the sidecar write fails after JSON creation, raise and leave the JSON as evidence instead of overwriting it.

- [ ] **Step 4: Write failing artifact and BM25 semantic-equivalence tests**

```python
def test_jsonl_fingerprint_tracks_file_rows_ids_and_semantics(tmp_path):
    root = tmp_path
    path = root / "child_blocks.jsonl"
    write_jsonl(path, [{"child_id": "c2", "text": "B"}, {"child_id": "c1", "text": "A"}])
    fp = fingerprint_jsonl(path, project_root=root, id_field="child_id", require_unique_ids=True)
    assert fp.row_count == 2
    assert fp.id_count == 2
    assert fp.unique_id_count == 2
    assert fp.relative_path == "child_blocks.jsonl"
    assert len(fp.sha256) == len(fp.ids_sha256) == len(fp.semantic_sha256) == 64


def test_bm25_fingerprint_requires_semantic_equality_with_source_rows(tmp_path):
    source = [{"child_id": "c1", "text": "A"}, {"child_id": "c2", "text": "B"}]
    path = tmp_path / "child_bm25.json"
    path.write_text(json.dumps({"records": [
        {"id": "c2", "child_id": "c2", "text": "B"},
        {"id": "c1", "child_id": "c1", "text": "A"},
    ]}, ensure_ascii=False), encoding="utf-8")
    fp = fingerprint_bm25(path, project_root=tmp_path, source_rows=source, source_id_field="child_id")
    assert fp.row_count == 2
    broken = json.loads(path.read_text(encoding="utf-8"))
    broken["records"][0]["text"] = "changed"
    path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="BM25 semantic corpus differs"):
        fingerprint_bm25(path, project_root=tmp_path, source_rows=source, source_id_field="child_id")
```

- [ ] **Step 5: Implement artifact/BM25 fingerprints without loading raw crawler files**

Use row-multiset semantics: canonicalize each row independently, sort canonical row bytes, then hash each row plus LF. For BM25, require a JSON object with a list field `records`, verify every `record["id"] == record[source_id_field]`, remove only the derived `id` field, and compare the resulting row multiset to the source artifact. Do not deduplicate media rows because repeated media IDs are valid occurrences.

- [ ] **Step 6: Add sanitizer tests and implementation**

The sanitizer must expose only known codes, component labels, hashes, counts and relative evidence paths. Add tests that feed drive-letter paths, UNC paths, `MINIO_SECRET_KEY`, and source text into issue details and assert the serialized public result contains none of them. Unknown internal exceptions map to `verification_internal_error` and only expose the exception class name.

- [ ] **Step 7: Run and review the focused test file**

Run: `conda run -n langchain python -m pytest tests/test_huiji_provenance.py -q`

Expected: all Task 1 tests pass; no network or infrastructure client is created.

---

### Task 2: Canonical Milvus Business Projection And Read-Only Fingerprint

**Corresponding specs:** `SOURCE-GATE-P0-02`, `RUNTIME-GATE-P0-02`, `RUNTIME-GATE-P0-06`, `SHADOW-BUILD-P0-05`

**Files:**
- Modify: `src/rag/vectorstore.py:15-146`
- Modify: `src/huiji_rag/provenance.py`
- Modify: `tests/test_vectorstore.py`
- Modify: `tests/test_huiji_provenance.py`

**Interfaces:**
- Produces: `HUIJI_BUSINESS_FIELDS`, `huiji_child_to_business_row()`, `MilvusFingerprint`, `normalize_milvus_schema()`, `capture_milvus_fingerprint()`.
- Consumers: runtime verifier, deep audit and shadow builder.
- Read contract: Milvus queries request the primary key and non-vector business fields only; `embedding` is never requested.

- [ ] **Step 1: Write a failing projection-consistency test**

```python
def test_huiji_milvus_row_uses_one_business_projection():
    child = {"child_id": "c1", "text": "正文", "parent_id": "p1", "source_refs": [{"kind": "data_page"}]}
    business = huiji_child_to_business_row(child)
    row = huiji_child_to_milvus_row(child, [0.1, 0.2])
    assert row == {**business, "embedding": [0.1, 0.2]}
    assert tuple(business) == HUIJI_BUSINESS_FIELDS
    assert "embedding" not in business
    assert business["id"] == business["child_id"] == "c1"
```

- [ ] **Step 2: Extract the current row mapping into the pure business projection**

Keep the current serialization exactly: JSON-string fields remain `ensure_ascii=False`; integer defaults remain unchanged. Define `HUIJI_BUSINESS_FIELDS` in insertion order and make `huiji_child_to_milvus_row()` add only `embedding` to the shared projection.

- [ ] **Step 3: Write failing fake-Milvus fingerprint tests**

The fake client must record all method calls and raise if `insert`, `delete`, `upsert`, `create_collection` or `drop_collection` is invoked. Cover:

```python
fp = capture_milvus_fingerprint(fake_client, "active_v3")
assert fp.row_count == 2
assert fp.primary_ids_sha256 == expected_id_hash
assert fp.business_fields_sha256 == expected_business_hash
assert "embedding" not in fake_client.output_fields
assert fake_client.mutation_calls == []
```

Also assert duplicate IDs, row-count disagreement, missing primary field and missing business field raise a typed `ProvenanceValidationError` with the corresponding stable code.

- [ ] **Step 4: Implement collection-agnostic schema and full business-field fingerprints**

```python
@dataclass(frozen=True)
class MilvusFingerprint:
    database: str
    collection: str
    schema_sha256: str
    row_count: int
    primary_field: str
    primary_id_count: int
    primary_ids_sha256: str
    business_fields_sha256: str
```

`normalize_milvus_schema()` must retain schema field name, data type, primary/auto-id flags, dimension/max-length/type params and dynamic-field setting while omitting collection name, aliases, load state and timestamps. `capture_milvus_fingerprint()` must use `query_iterator(batch_size=1000, limit=-1, filter="", output_fields=list(HUIJI_BUSINESS_FIELDS))`, close the iterator in `finally`, sort by primary ID, reject duplicates, and compare queried count with `get_collection_stats()`.

- [ ] **Step 5: Run projection and Milvus fingerprint tests**

Run: `conda run -n langchain python -m pytest tests/test_vectorstore.py tests/test_huiji_provenance.py -q`

Expected: all tests pass and mutation spy count remains zero.

---

### Task 3: Full Offline Source Audit And Baseline Installation

**Corresponding specs:** `SOURCE-GATE-P0-01..05`

**Files:**
- Modify: `src/huiji_rag/provenance.py`
- Create: `scripts/audit_huiji_provenance.py`
- Modify: `tests/test_huiji_provenance.py`

**Interfaces:**
- Produces: `audit_huiji_provenance(cfg, client) -> AuditResult`, `build_baseline_candidate()`, `install_baseline_create_new()`.
- CLI: `audit --run-dir <new-dir> --candidate-baseline <new-file>` and `install-baseline --candidate <file> --output <new-file>`.
- Output: `audit.v1.json`, `audit.v1.json.sha256`, optional `baseline.candidate.v1.json` plus sidecar.

- [ ] **Step 1: Write exact source-ref and media reverse-reference tests**

Build a temporary raw snapshot with one `data_pages.jsonl` row and one `resources_manifest.jsonl` row, then artifacts that reference them. Assert pass only when:

```text
source_ref.kind == data_page
source_ref.title == raw.title
source_ref.revid == raw.revid
source_ref.content_sha256 == raw.content_sha256
media.sha1 == resource.sha1
media.local_relpath == resource.local_relpath
media.source_url == resource.url
```

Create separate failing tests for blank `source_refs`, illegal source kind, missing raw tuple, revision mismatch, content hash mismatch, missing resource tuple, SHA-1 mismatch, path mismatch and URL mismatch. Each test must assert a stable issue code and that no candidate baseline is created.

Define the cross-task result type before implementing the audit:

```python
@dataclass(frozen=True)
class AuditResult:
    status: Literal["pass", "blocked", "error"]
    issues: tuple[VerificationIssue, ...]
    raw_snapshot: Mapping[str, Mapping[str, object]]
    artifacts: Mapping[str, ArtifactFingerprint]
    bm25: Mapping[str, Bm25Fingerprint]
    milvus: MilvusFingerprint | None
    counters: Mapping[str, int]
    audit_evidence_relpath: str = ""
    audit_evidence_sha256: str = ""
```

- [ ] **Step 2: Write failing baseline provenance tests**

```python
def test_baseline_candidate_requires_passed_full_audit(tmp_path):
    result = make_audit_result(status="blocked")
    with pytest.raises(ProvenanceValidationError, match="audit_not_passed"):
        build_baseline_candidate(result)


def test_install_baseline_is_create_new_and_checks_audit_hash(tmp_path):
    candidate = write_candidate(tmp_path, audit_sha256="a" * 64)
    audit = tmp_path / "audit.v1.json"
    audit.write_bytes(b"different\n")
    with pytest.raises(ProvenanceValidationError, match="audit_evidence_mismatch"):
        install_baseline_create_new(candidate, tmp_path / "installed.json")
```

- [ ] **Step 3: Implement streaming raw lookup and exact reverse-reference audit**

Index crawler pages by `(title, int(revid), content_sha256)` and resources by `(sha1.lower(), normalized_posix_local_relpath, url)`. Iterate parent and child rows, require a non-empty list of refs, and count every occurrence. Iterate media rows without deduplicating occurrences. Evidence must contain counts and issue summaries only, with at most hash/ID samples; it must not copy source text or full raw rows.

- [ ] **Step 4: Implement BM25 and active Milvus audit closure**

The audit must:

1. fingerprint parent, child and media artifacts;
2. prove child/media BM25 semantic equality to their source artifacts;
3. capture active Milvus through `capture_milvus_fingerprint()`;
4. compare the active Milvus primary IDs and business projection against `huiji_child_to_business_row()` for every child;
5. verify `cfg.huiji.enabled`, `cfg.huiji.source_mode`, build version, processed root containment, `cfg.huiji.text_collection_name`, and `cfg.vectorstore.collection_name`;
6. return every safely-computable issue in stable `(code, component, expected, actual)` order.

- [ ] **Step 5: Implement candidate schema and create-new install**

The baseline JSON must have these top-level keys and no absolute path:

```json
{
  "schema_version": "huiji.provenance_baseline/v1",
  "source_mode": "huiji_crawler",
  "build_version": "dev",
  "raw_snapshot": {},
  "artifacts": {},
  "bm25": {},
  "milvus": {},
  "audit_evidence": {"relative_path": "...", "sha256": "..."},
  "generated_at_utc": "...",
  "generator_version": "1"
}
```

`artifacts` contains parent/child/media fingerprints; `bm25` contains child/media file and semantic fingerprints; `milvus` contains database, active collection, normalized schema, row, ID and business-field fingerprints. The installer verifies the candidate sidecar and referenced audit hash, then writes the destination and sidecar with `xb`.

- [ ] **Step 6: Implement CLI exit contracts and safety tests**

Exit codes:

```text
0 audit/install passed
2 provenance blocked
3 validator internal error
```

Patch candidate/evidence writers to raise on a second invocation and assert existing files remain byte-identical. Patch Milvus mutation methods to raise and confirm `audit` still passes with zero mutation calls.

- [ ] **Step 7: Run the offline audit test set**

Run: `conda run -n langchain python -m pytest tests/test_huiji_provenance.py -q`

Expected: pass, including all source/media mismatch cases and create-new gates.

---

### Task 4: Fast Runtime Verifier And Config Pinning

**Corresponding specs:** `SOURCE-GATE-P0-01..03`, `RUNTIME-GATE-P0-02`, `RUNTIME-GATE-P0-03`, `RUNTIME-GATE-P0-05`, `RUNTIME-GATE-P0-06`

**Files:**
- Modify: `config/config.py:72-88,146-235`
- Modify: `config/settings.yaml:45-51`
- Modify: `src/huiji_rag/provenance.py`
- Create: `scripts/verify_huiji_runtime.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_huiji_provenance.py`

**Interfaces:**
- Adds: `HuijiCfg.source_mode: str`, `HuijiCfg.provenance_baseline: Path`.
- Produces: `verify_runtime(cfg, *, client_factory=MilvusClient) -> VerificationResult`.
- CLI default baseline comes only from `cfg.huiji.provenance_baseline`.

- [ ] **Step 1: Write failing config tests**

```python
assert cfg.huiji.source_mode == "huiji_crawler"
assert cfg.huiji.provenance_baseline == cfg.paths.project_root / "config/provenance/huiji-dev.v1.json"
```

Add to settings:

```yaml
huiji:
  source_mode: "huiji_crawler"
  provenance_baseline: "config/provenance/huiji-dev.v1.json"
```

- [ ] **Step 2: Write runtime pass and drift tests**

Use a temporary project root and fake read-only Milvus client. Cover baseline missing/invalid, source mode mismatch, build mismatch, processed-root escape, collection config mismatch, artifact missing/hash/count/ID mismatch, Milvus collection/schema/row/ID/content mismatch and client exception. Assert all non-internal mismatches yield `blocked`; unexpected exceptions yield `error`; both have `allowed is False`.

- [ ] **Step 3: Write a raw-access and mutation-spy test**

Patch access to `data_pages.jsonl` and `resources_manifest.jsonl` to raise `AssertionError("raw crawler scanned")`. Patch all Milvus mutation methods to raise. Runtime verification against valid artifact and fake Milvus fingerprints must pass, proving the fast path does not scan raw or mutate infrastructure.

- [ ] **Step 4: Implement ordered fail-closed verification**

Verification order must be baseline parse/self-hash, config, contained artifact paths, artifact/BM25 fingerprints, then Milvus. If Milvus connection fails, emit only `verification_internal_error` for that component rather than fabricated schema/row/ID/content mismatches. Never create or update baseline from this function.

- [ ] **Step 5: Implement runtime CLI and hash-pinned output**

CLI options:

```text
--run-dir <new-dir>     optional; default eval/huiji_provenance/<UTC>-runtime-<nonce>
```

The CLI always reads the configured baseline and exposes no baseline/config override. It writes `runtime.v1.json` plus sidecar, prints one compact line containing `status`, sorted error codes and project-relative evidence path, and exits `0` for pass, `2` for blocked, `3` for internal error.

- [ ] **Step 6: Run config and runtime verifier tests**

Run: `conda run -n langchain python -m pytest tests/test_config.py tests/test_huiji_provenance.py -q`

Expected: pass; no baseline is created by runtime tests.

---

### Task 5: FastAPI Fail-Closed Integration

**Corresponding specs:** `RUNTIME-GATE-P0-01..04`, `SOURCE-GATE-P0-05`

**Files:**
- Modify: `backend/schemas.py:254-258`
- Modify: `backend/main.py:59-151`
- Create: `tests/test_backend_provenance_gate.py`

**Interfaces:**
- `/health` adds `provenance_status`, `provenance_errors`, `provenance_evidence`.
- `_verify_provenance_once()` caches one startup result.
- `_ensure_loaded()` must call `_verify_provenance_once()` before `load_vectorstore()`.

- [ ] **Step 1: Write blocked/error backend tests before implementation**

```python
def test_blocked_provenance_never_constructs_rag(monkeypatch):
    monkeypatch.setattr(main_mod, "verify_runtime", lambda _cfg: blocked_result("artifact_hash_mismatch"))
    monkeypatch.setattr(main_mod, "load_vectorstore", lambda _cfg: pytest.fail("vectorstore loaded"))
    reset_backend_state(main_mod)
    main_mod._ensure_loaded()
    assert main_mod._state["loaded"] is False
    assert main_mod._state["vs"] is None
    assert main_mod._state["retriever"] is None
    assert main_mod._state["chain"] is None
```

Repeat for verifier exception and assert it maps to provenance `error` without constructing RAG.

- [ ] **Step 2: Write health-only API tests**

With blocked provenance, assert `/health` returns HTTP 200, `status == "error"`, `vectorstore_loaded is False`, safe error codes and no drive-letter/UNC/secret/source text. Assert `/ask`, `/ask/stream`, and `/api/media/voice/page` return 503 and do not invoke chain or media registry methods.

- [ ] **Step 3: Extend the health schema**

```python
class HealthResponse(BaseModel):
    status: str
    vectorstore_loaded: bool
    llm_ready: bool
    doc_count: int
    provenance_status: Literal["pending", "pass", "blocked", "error"] = "pending"
    provenance_errors: list[str] = Field(default_factory=list)
    provenance_evidence: str = ""
```

- [ ] **Step 4: Add one cached startup gate shared by startup and direct `_ensure_loaded()`**

Initialize state keys `provenance_checked=False` and `provenance=None`. `_verify_provenance_once()` catches unexpected exceptions into a sanitized error result and caches it. `_ensure_loaded()` returns immediately unless `result.allowed`; only then may it call `load_vectorstore`, `Retriever` and `RAGChain`. `/health` reports the cached result. Do not add a bypass environment variable.

- [ ] **Step 5: Write and pass the allowed-path test**

Patch verifier to pass and constructors to fakes; call `_ensure_loaded()` twice. Assert verifier and each constructor run exactly once and state becomes loaded. This proves the gate is not repeatedly hashing artifacts on every health request.

- [ ] **Step 6: Run backend regression tests**

Run: `conda run -n langchain python -m pytest tests/test_backend_provenance_gate.py tests/test_categories.py tests/test_sse.py -q`

Expected: pass; existing answer/stream behavior is unchanged when provenance passes.

---

### Task 6: Launcher Gate And Removal Of Legacy Auto-Build

**Corresponding specs:** `RUNTIME-GATE-P0-01`, `RUNTIME-GATE-P0-03`, `LEGACY-BLOCK-P0-02`, `LEGACY-BLOCK-P0-03`

**Files:**
- Modify: `start.ps1:24-49`
- Modify: `start.bat:19-47`
- Modify: `tests/test_start_scripts.py`

**Interfaces:**
- Both launchers run `scripts/verify_huiji_runtime.py` after resolving Python and before checking/starting backend.
- Exit nonzero stops without starting backend or frontends.

- [ ] **Step 1: Add failing static order and forbidden-string tests**

For both scripts assert:

```python
assert "documents.jsonl" not in text
assert "extract_data.py" not in text
assert "scripts\\build_index.py" not in text
assert "verify_huiji_runtime.py" in text
assert text.index("verify_huiji_runtime.py") < text.index("uvicorn")
```

Also assert no `PROVENANCE_SKIP`, `FORCE`, `fallback` or equivalent bypass token is introduced.

- [ ] **Step 2: Replace the PowerShell legacy block with the verifier gate**

```powershell
Write-Host "[step] 验证 Huiji RAG provenance..." -ForegroundColor Yellow
& $py scripts\verify_huiji_runtime.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] Huiji RAG provenance 未通过，后端和前端均未启动" -ForegroundColor Red
    Read-Host
    exit 1
}
```

- [ ] **Step 3: Replace the Batch legacy block with the verifier gate**

```bat
echo [step] 验证 Huiji RAG provenance...
"%PY%" scripts\verify_huiji_runtime.py
if errorlevel 1 (
    echo [错误] Huiji RAG provenance 未通过，后端和前端均未启动
    pause
    exit /b 1
)
```

- [ ] **Step 4: Tighten launcher health readiness**

PowerShell must require both `$h.status -eq "ok"` and `$h.provenance_status -eq "pass"`. Batch JSON check must require both fields. Keep the existing 60-second timeout and child-process cleanup behavior.

- [ ] **Step 5: Run launcher tests**

Run: `conda run -n langchain python -m pytest tests/test_start_scripts.py -q`

Expected: pass; no legacy data or builder path remains in either launcher.

---

### Task 7: Fail-Closed Legacy CLI Tombstones

**Corresponding specs:** `LEGACY-BLOCK-P0-01`, `LEGACY-BLOCK-P0-03`

**Files:**
- Modify: `scripts/extract_data.py`
- Modify: `scripts/build_index.py`
- Modify: `scripts/build_assets.py`
- Create: `tests/test_legacy_rag_cli_blocked.py`

**Interfaces:**
- Each `main()` raises `SystemExit(64)` with a stable `legacy_obsidian_pipeline_disabled` message.
- No config, vault reader, embedding, Milvus or MinIO client is imported or initialized by `main()`.

- [ ] **Step 1: Write subprocess exit tests for all three scripts**

Parameterize the three paths and assert exit code `64`, stderr contains `legacy_obsidian_pipeline_disabled` and `docs/huiji-rag-runbook.md`, and stdout/stderr do not contain credentials or absolute paths.

- [ ] **Step 2: Write import/call-order mutation-spy tests**

Load each script module, monkeypatch any surviving old callable names to raise `AssertionError`, invoke `main()`, and assert only `SystemExit(64)` occurs. The test must also snapshot a temporary vault, artifact, settings and fake infrastructure state before/after and assert byte equality.

- [ ] **Step 3: Replace each old CLI body with the same minimal tombstone contract**

```python
LEGACY_EXIT_CODE = 64
LEGACY_MESSAGE = (
    "legacy_obsidian_pipeline_disabled: this command cannot mutate RAG data; "
    "use docs/huiji-rag-runbook.md"
)

def main() -> NoReturn:
    print(LEGACY_MESSAGE, file=sys.stderr)
    raise SystemExit(LEGACY_EXIT_CODE)
```

Keep the files in place; do not add any environment-variable bypass.

- [ ] **Step 4: Run tombstone and launcher tests together**

Run: `conda run -n langchain python -m pytest tests/test_legacy_rag_cli_blocked.py tests/test_start_scripts.py -q`

Expected: pass; mutation initialization count is zero.

---

### Task 8: Create-New Huiji Shadow Builder

**Corresponding specs:** `SHADOW-BUILD-P0-01..07`, `RUNTIME-GATE-P0-06`

**Files:**
- Modify: `src/rag/vectorstore.py:455-507`
- Create: `scripts/build_huiji_index.py`
- Create: `tests/test_huiji_shadow_builder.py`

**Interfaces:**
- Produces: `build_huiji_shadow_collection(cfg, children, *, collection_name, active_collection_names, ...) -> int`.
- CLI requires `--collection-name`; optional tuning flags may only cover batch size/delay/retries and run directory.
- CLI must not expose `--force`, `--replace`, `--drop-existing`, `--activate` or config-write options.

- [ ] **Step 1: Write parser and precondition tests**

Assert missing `--collection-name` is argparse exit 2. Assert active names from both config and baseline are rejected. Assert an existing target is rejected. In all three cases, spies prove embedding factory, `create_collection`, `insert`, `delete`, `drop_collection`, settings writes and evidence overwrite are zero.

- [ ] **Step 2: Write provenance-before-embedding/mutation tests**

Patch `verify_runtime()` to blocked/error and assert the builder writes failure evidence but calls neither embedding nor any Milvus mutation. Patch the child artifact after a pass result and assert the builder rechecks its SHA before mutation and stops.

- [ ] **Step 3: Replace the unsafe Huiji helper with create-new semantics**

`build_huiji_shadow_collection()` must:

1. reject blank/unsafe collection names and every active name before creating embeddings;
2. validate every child row with `validate_huiji_child_for_milvus()`;
3. create a direct `MilvusClient` and stop with `FileExistsError` when target exists;
4. call `ensure_huiji_collection()` once for the new target;
5. get embeddings only after collection creation and insert batches using `huiji_child_to_milvus_row()`;
6. retain current retry and delay behavior;
7. flush and return inserted count;
8. never mutate `cfg.vectorstore.collection_name` and never call `_delete_existing_entities()`.

- [ ] **Step 4: Write successful fake-build verification tests**

Use three generic child rows and deterministic vectors. Assert the target is created once, all rows inserted, active config remains byte/object equal, and post-build `capture_milvus_fingerprint()` equals the expected child row count, ID hash and business hash.

- [ ] **Step 5: Write post-build mismatch and failure-evidence tests**

Simulate schema, row, ID and business-field mismatch separately. Each must exit nonzero, write `shadow-build.v1.json` plus sidecar with `status=blocked` or `status=error`, retain the target, and never activate/delete it. Simulate an embedding failure after collection creation and assert the failed target is retained and registered in evidence.

- [ ] **Step 6: Implement the CLI with phase-labelled evidence**

Evidence must include relative baseline/artifact references, baseline SHA, target database/collection, precondition result, inserted count, post-build fingerprint, config file pre/post SHA, status, stable failure code, duration and timestamps. It must not include vectors, text, prompts, API errors containing credentials or absolute paths.

- [ ] **Step 7: Run shadow builder tests**

Run: `conda run -n langchain python -m pytest tests/test_huiji_shadow_builder.py tests/test_vectorstore.py -q`

Expected: pass; every unsafe path stops before embedding or mutation.

---

### Task 9: Protected-State Acceptance Harness And Current-Source Documentation

**Corresponding specs:** all P0 evidence/real-acceptance clauses; no P1/P2 implementation

**Files:**
- Create: `scripts/verify_huiji_provenance_acceptance.py`
- Create: `tests/test_huiji_source_docs.py`
- Modify: `README.md:1-20`
- Modify: `docs/architecture.md:1-45`
- Modify: `docs/huiji-rag-runbook.md:1-70`

**Interfaces:**
- Acceptance CLI subcommands: `snapshot`, `compare`, `sample-active`, `prove-artifact-drift`.
- `snapshot` uses existing `capture_protected_snapshot()` and hash-pinned create-new output.
- `compare` recaptures current protected state and fails on active Milvus, MinIO, MySQL or formal artifact drift.
- `sample-active` dynamically derives entities from current artifacts; no role or count is hardcoded.

- [ ] **Step 1: Write failing acceptance payload tests**

Use fake protected snapshots to assert capture strips no protected field, compare ignores capture timestamps only, and any active Milvus schema/row/ID, MinIO inventory, MySQL table or artifact hash change returns `protected_state_drift`. Assert adding the separately named shadow collection is not treated as active-collection drift.

- [ ] **Step 2: Implement protected snapshot and comparison subcommands**

Commands:

```powershell
python scripts/verify_huiji_provenance_acceptance.py snapshot --output <new-json>
python scripts/verify_huiji_provenance_acceptance.py compare --before <json> --output <new-json>
```

Both outputs are canonical/create-new/hash-pinned. `compare` writes its result even on drift, exits `0` only for equality and `2` for drift. Infrastructure access remains read-only.

- [ ] **Step 3: Implement dynamic active-source sampling**

Load `EvaluationInventory`, select up to one deterministic entity per available `entity_type`, select an existing child and an intent derived from its `route_tags`/`section_kind`, construct a `QueryPlan` with that entity's current ID/name/type, then call the active `Retriever.search()`. Require non-empty sources, matching owner and `retrieval_stage == "huiji_hybrid"` for every source. Output only entity/child hashes, entity type, counts and stage values; do not write names or question text.

Add `prove-artifact-drift`: copy only the installed baseline and its protected artifact/BM25 inputs into a temporary directory, create a temporary `Config` copy whose Huiji paths point there, mutate one byte in the temporary child artifact, call the library verifier, and require `artifact_hash_mismatch`. The command must never alter project config/formal artifacts, must delete the temporary directory in `finally`, and must not expose a baseline override to the runtime CLI, launcher or backend.

- [ ] **Step 4: Write documentation assertions before editing docs**

Tests must require:

- README top section says `huiji_crawler`, current v3 collection, provenance gate and old commands disabled.
- Architecture current data flow starts from Huiji crawler and labels Obsidian flow historical.
- Runbook contains exact `audit`, `install-baseline`, `verify_huiji_runtime.py` and `build_huiji_index.py --collection-name` commands.
- Runbook forbids activation, deletion, overwrite and Obsidian rollback.
- None of these current sections instructs execution of the three tombstoned CLIs.

- [ ] **Step 5: Make the minimal P0 documentation changes**

Do not rewrite all historical documentation. Add an authoritative current-status banner to README, replace the current architecture header/data-flow with Huiji provenance flow, explicitly mark the old Obsidian text as historical, and rewrite the unsafe runbook build/switch/rollback sections to shadow-only operation. Record that P1 performs broader historical cleanup.

- [ ] **Step 6: Run acceptance harness and docs tests**

Run: `conda run -n langchain python -m pytest tests/test_huiji_source_docs.py tests/test_huiji_provenance.py tests/test_huiji_shadow_builder.py -q`

Expected: pass; docs expose no executable legacy rebuild instruction in current sections.

---

### Task 10: Generate And Install The Real Huiji Baseline

**Corresponding specs:** `SOURCE-GATE-P0-01..05`, `RUNTIME-GATE-P0-02..06`

**Files:**
- Create by audited CLI: `config/provenance/huiji-dev.v1.json`
- Create by audited CLI: unique files under `eval/huiji_provenance/<run-id>/`

**Interfaces:**
- Consumes the completed implementation and current active data.
- Produces the sole installed P0 baseline and deep-audit evidence.

- [ ] **Step 1: Run the complete non-real-build test suite before touching infrastructure**

Run:

```powershell
conda run -n langchain python -m pytest `
  tests/test_huiji_provenance.py `
  tests/test_backend_provenance_gate.py `
  tests/test_start_scripts.py `
  tests/test_legacy_rag_cli_blocked.py `
  tests/test_huiji_shadow_builder.py `
  tests/test_huiji_source_docs.py `
  tests/test_config.py `
  tests/test_vectorstore.py -q
```

Expected: all pass. Any failure blocks the real audit.

- [ ] **Step 2: Create a unique run directory and capture the pre-operation protected snapshot**

```powershell
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-huiji-source-p0'
$RunDir = Join-Path 'eval\huiji_provenance' $RunId
conda run -n langchain python scripts\verify_huiji_provenance_acceptance.py snapshot `
  --output "$RunDir\protected.pre.v2.json"
```

Expected: exit 0; JSON and `.sha256` exist; active Milvus, both configured MinIO scopes, protected MySQL tables and processed artifacts are represented.

- [ ] **Step 3: Run the full real deep audit and produce a candidate baseline**

```powershell
conda run -n langchain python scripts\audit_huiji_provenance.py audit `
  --run-dir "$RunDir\audit" `
  --candidate-baseline "$RunDir\baseline.candidate.v1.json"
```

Expected: exit 0; source/media/BM25/active-Milvus mismatch counts are zero. On any mismatch, stop, retain evidence, expand diagnosis and do not install a baseline.

- [ ] **Step 4: Mechanically review the candidate before installation**

Check schema/source mode/build version, relative paths, audit SHA linkage, artifact/BM25 hashes and counts, active database/collection, normalized schema, ID and business fingerprints. Scan the candidate and evidence for drive-letter paths, UNC paths, `access_key`, `secret`, `password`, source text and answer text. Any hit blocks installation.

- [ ] **Step 5: Install the candidate with create-new semantics**

```powershell
conda run -n langchain python scripts\audit_huiji_provenance.py install-baseline `
  --candidate "$RunDir\baseline.candidate.v1.json" `
  --output config\provenance\huiji-dev.v1.json
```

Expected: exit 0. If the destination already exists, compare hashes; do not overwrite it. A different existing hash is a blocking condition requiring investigation.

- [ ] **Step 6: Run the fast verifier against the installed baseline**

```powershell
conda run -n langchain python scripts\verify_huiji_runtime.py `
  --run-dir "$RunDir\runtime-pass"
```

Expected: `status=pass`, exit 0, no raw crawler files listed as runtime inputs.

- [ ] **Step 7: Prove controlled artifact drift blocks without modifying formal artifacts**

```powershell
conda run -n langchain python scripts\verify_huiji_provenance_acceptance.py prove-artifact-drift `
  --output "$RunDir\artifact-drift-proof.v1.json"
```

Expected: command exit 0 because the proof observed the required blocked result; evidence records `artifact_hash_mismatch`. Do not edit files under `data/processed/huiji/dev`.

---

### Task 11: Full Real Shadow Build And P0 Hard Acceptance

**Corresponding specs:** all 21 P0 requirements and Section 10 hard acceptance

**Files:**
- Create by CLIs: unique shadow-build and final acceptance evidence under the Task 10 run directory.
- No production config, artifact, MinIO or MySQL file may be modified.

- [ ] **Step 1: Prove the active target name is rejected before embedding**

Run the builder with the configured active name. Expected: exit nonzero, evidence says `active_collection_forbidden`, no embedding progress event appears, and protected state remains equal.

- [ ] **Step 2: Build one uniquely named full shadow collection**

```powershell
$Shadow = 'text_child_bge_m3_shadow_' + ($RunId.ToLower() -replace '[^a-z0-9_]', '_')
conda run -n langchain python scripts\build_huiji_index.py `
  --collection-name $Shadow `
  --run-dir "$RunDir\shadow-build"
```

Expected: full vectorization completes, evidence status is pass, and the collection remains non-active. If it fails, retain collection/evidence and stop the completion claim; do not delete or reuse the name.

- [ ] **Step 3: Verify the shadow against dynamic current artifact facts**

Read expected row count and hashes from the installed baseline, not constants. Require collection-agnostic schema equality, full row count, full primary ID set/fingerprint and full non-vector business-field fingerprint equality. Confirm `config/settings.yaml` and the installed baseline still select the original active collection.

Rerun the builder with the same `$Shadow` name. Expected: exit nonzero with `target_collection_exists`, no embedding progress event, no row deletion and no change to the retained shadow fingerprint.

- [ ] **Step 4: Run dynamic active-source sampling**

```powershell
conda run -n langchain python scripts\verify_huiji_provenance_acceptance.py sample-active `
  --output "$RunDir\active-source-sample.v1.json"
```

Expected: exit 0; every sampled entity type returns owned sources and every source has `retrieval_stage=huiji_hybrid`. No fixed character, skill count, line count or language count appears in code or evidence.

- [ ] **Step 5: Capture and compare the post-operation protected state**

```powershell
conda run -n langchain python scripts\verify_huiji_provenance_acceptance.py compare `
  --before "$RunDir\protected.pre.v2.json" `
  --allow-shadow-collection $Shadow `
  --output "$RunDir\protected.compare.v2.json"
```

Expected: exit 0 and no changes to active Milvus, existing MinIO objects, MySQL or formal artifacts. New `a-bucket` objects are allowed only when every allowed key contains the exact Milvus collection ID or persistent segment ID of `$Shadow`; unrelated additions still block. The retained non-active shadow is the only allowed infrastructure addition.

- [ ] **Step 6: Smoke both startup paths**

Run `scripts/verify_huiji_runtime.py` directly, then start uvicorn directly and inspect `/health`; stop it, then launch through `start.ps1` and inspect `/health`. Both paths must report `provenance_status=pass` before RAG is loaded. Repeat with a test-only mismatched baseline on an isolated port; `/health` remains available while ask/stream/media return 503.

- [ ] **Step 7: Run the complete regression suite**

Run: `conda run -n langchain python -m pytest -q`

Expected: all tests pass. Existing unrelated failures must be identified by exact test and shown not to be caused by this change; any failure in files touched by this plan blocks P0 completion.

- [ ] **Step 8: Produce the final requirement matrix and independent review packet**

Create hash-pinned `p0-acceptance.v1.json` in the run directory with one record for each P0 ID, implementation file, test command/result, real evidence reference and pass/blocked status. Scan all new baseline/evidence files for forbidden content and scan production code/tests for hardcoded current row count or character-specific acceptance. Keep the shadow collection registered and non-active.

---

## 3. Deferred / Out Of Scope

- P1 removal of tombstoned legacy modules, Obsidian config fields and broad historical documentation cleanup requires a separate spec/plan approval.
- P2 deletion of local legacy data, MinIO legacy/orphan objects and MySQL Obsidian supplements requires fresh backup, frozen inventory and hash-pinned operation plan.
- Planner intent coverage, answer grounding, media pagination quality and retrieval latency remain separate RAG quality work; they cannot be used to waive this provenance gate.
- This plan does not activate the shadow collection, switch aliases, alter embedding models, rebuild MinIO, or modify Wiki data.

## 4. Completion Self-Check

- [ ] `SOURCE-GATE-P0-01..05` each has passing unit evidence and real audit evidence.
- [ ] `RUNTIME-GATE-P0-01..06` each passes launcher, direct backend and controlled-drift checks.
- [ ] `LEGACY-BLOCK-P0-01..03` each proves zero mutation-client initialization.
- [ ] `SHADOW-BUILD-P0-01..07` each passes fake tests and the full real shadow build.
- [ ] Installed baseline is linked to a passed deep audit and uses create-new/hash-pinned files.
- [ ] Runtime verifier does not scan raw crawler files or write any business store.
- [ ] Active and shadow collection fingerprints match the approved dynamic child artifact facts.
- [ ] Pre/post active Milvus, MinIO, MySQL and formal artifact snapshots are equal.
- [ ] Shadow is retained, registered and non-active; no collection or object was deleted.
- [ ] All new public/evidence outputs contain no absolute path, credential, source content, question or answer text.
- [ ] No fixed character or current row count is used as a generic production/test constant.
- [ ] Full pytest and P0 acceptance matrix pass before completion is declared.
