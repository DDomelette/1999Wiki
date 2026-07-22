# RAG Full-Chain Evaluation v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backward-compatible v2 RAG evaluation policy that validates the current generation-based release, snapshots only active MinIO objects, evaluates current intent/media contracts, and produces a consolidated metrics document plus a dated full-project report.

**Architecture:** Keep the existing M1–M5 runner, but add `release.py` for active release identity, `protected_minio.py` for metadata-only scoped snapshots, and `taxonomy.py` for policy-bound intent/section mappings. Existing inventory, deterministic evaluation, reporting, and runner modules consume these focused interfaces; v1 files remain readable while new runs default to `rag_eval.thresholds/v2`.

**Tech Stack:** Python 3.11, dataclasses, pytest, MinIO Python SDK, pymilvus, PyMySQL, FastAPI HTTP/SSE, JSON/JSONL, Markdown, existing Huiji runtime artifacts.

## Global Constraints

- Governing spec: `docs/superpowers/specs/2026-07-23-rag-full-chain-evaluation-v2-design.md`.
- Preserve M1–M5, D1–D4, severity ordering, dynamic sampling, and deterministic hard gates.
- Preserve v1 thresholds, reports, and evidence without rewriting them.
- New policy schema: `rag_eval.thresholds/v2`.
- P0 intents: `intro`, `profile_fact`, `skill`, `item`, `culture`, `udimo`, `voice`, `media`, `video`, `psychube`, `story`, `general_game`, `meta_question`.
- Minimums: 48 unique cases, D1/D2/D3/D4 = 16/12/12/8, 8 entities, 10% repeats.
- Difficulty targets/floors stay D1 90/85, D2 85/78, D3 80/70, D4 90/85.
- Success rate stays `>=98%`; retrieval/TTFT/total P95 stay `<=5s/15s/45s`.
- Local-path and cross-entity leaks remain zero-tolerance.
- Never mutate Milvus, MinIO, MySQL, active pointer, provenance, or processed artifacts.
- Do not modify `frontend/**`, `kimi_web/**`, or `.worktrees/main-mobile-responsive/**`; do not run npm, Vite, Playwright, or frontend builds.
- Real evaluation uses an isolated backend port and never occupies 5173, 3000, or 3007.
- Never fabricate adjudication or human-audit results.

## File Map

| File | Responsibility |
|---|---|
| `eval/rag_full_chain_thresholds.v2.json` | Reviewed v2 policy |
| `src/rag_eval/contracts.py` | v1/v2 loading and run policy metadata |
| `src/rag_eval/release.py` | Active release identity and joint-health validation |
| `src/rag_eval/protected_minio.py` | Exact-key, metadata-only MinIO snapshots |
| `src/rag_eval/taxonomy.py` | Intent labels and section mappings |
| `src/rag_eval/inventory.py` | Protected snapshot composition |
| `src/rag_eval/sampling.py` | Build/schema/taxonomy-bound sampling |
| `src/rag_eval/deterministic.py` | v3 media binding gates |
| `src/rag_eval/reporting.py` | Consolidated result rendering |
| `src/rag_eval/runner.py` | v2 orchestration |
| `scripts/render_rag_evaluation_report.py` | Dated project report CLI |
| `docs/evaluation/rag-full-chain-v2.md` | Single current metrics reference |
| `docs/reports/2026-07-23-project-full-evaluation-v2.md` | Current result |

---

### Task 1: Versioned V2 Policy With V1 Read Compatibility

**Files:**
- Create: `eval/rag_full_chain_thresholds.v2.json`
- Modify: `src/rag_eval/contracts.py:40-50, 160-176, 230-324`
- Modify: `src/rag_eval/runner.py:56, 94-106, 263-278, 693-739`
- Test: `tests/test_rag_eval_contracts.py`
- Test: `tests/test_rag_eval_runner.py`

**Interfaces:**
- Consumes: `Thresholds`, `RunManifest`, `load_thresholds(path)`.
- Produces: `REVIEWED_P0_INTENTS_V2`, v1/v2-aware `load_thresholds`, `RunManifest.policy_version`, and `RunManifest.release_identity`.

- [ ] **Step 1: Write failing compatibility tests**

```python
def test_threshold_loader_accepts_v1_history_and_v2_current_policy(tmp_path: Path):
    v1 = load_thresholds(Path("eval/rag_full_chain_thresholds.v1.json"))
    payload = json.loads(Path("eval/rag_full_chain_thresholds.v1.json").read_text("utf-8"))
    payload["schema_version"] = "rag_eval.thresholds/v2"
    payload["p0_intents"].insert(5, "udimo")
    path = tmp_path / "thresholds.v2.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    v2 = load_thresholds(path)
    assert v1.schema_version == "rag_eval.thresholds/v1"
    assert v2.schema_version == "rag_eval.thresholds/v2"
    assert "udimo" in v2.p0_intents


def test_current_policy_rejects_missing_udimo(tmp_path: Path):
    payload = json.loads(Path("eval/rag_full_chain_thresholds.v1.json").read_text("utf-8"))
    payload["schema_version"] = "rag_eval.thresholds/v2"
    path = tmp_path / "invalid.v2.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewed v2 P0 intent list"):
        load_thresholds(path)


def test_runner_defaults_to_current_v2_policy():
    assert DEFAULT_THRESHOLDS_PATH == Path("eval/rag_full_chain_thresholds.v2.json")


def test_run_cli_accepts_an_explicit_thresholds_file():
    args = build_parser().parse_args([
        "run", "--base-url", "http://127.0.0.1:18000",
        "--seed", "20260723", "--output-root", "eval/rag_full_chain",
        "--thresholds", "eval/rag_full_chain_thresholds.v2.json",
    ])
    assert args.thresholds == Path("eval/rag_full_chain_thresholds.v2.json")
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_contracts.py tests/test_rag_eval_runner.py -q
```

Expected: v2 unsupported and runner still defaults to v1.

- [ ] **Step 3: Create the reviewed v2 JSON**

Copy every v1 numeric threshold unchanged, set `schema_version` to `rag_eval.thresholds/v2`, and insert `udimo` after `culture`. The exact P0 list is the Global Constraints list.

- [ ] **Step 4: Implement explicit schema-to-intent validation**

```python
REVIEWED_P0_INTENTS_V1 = (
    "intro", "profile_fact", "skill", "item", "culture", "voice",
    "media", "video", "psychube", "story", "general_game", "meta_question",
)
REVIEWED_P0_INTENTS_V2 = (
    "intro", "profile_fact", "skill", "item", "culture", "udimo", "voice",
    "media", "video", "psychube", "story", "general_game", "meta_question",
)
REVIEWED_P0_INTENTS_BY_SCHEMA = {
    "rag_eval.thresholds/v1": REVIEWED_P0_INTENTS_V1,
    "rag_eval.thresholds/v2": REVIEWED_P0_INTENTS_V2,
}
reviewed = REVIEWED_P0_INTENTS_BY_SCHEMA.get(schema_version)
if reviewed is None:
    raise ValueError(f"unsupported thresholds schema_version: {schema_version}")
if p0_intents != reviewed:
    label = "v2 " if schema_version.endswith("/v2") else ""
    raise ValueError(f"p0_intents differs from the reviewed {label}P0 intent list")
```

Keep the existing `schema_version` default and add two defaulted manifest fields so historical test constructors still work. Import `field` from `dataclasses`:

```python
policy_version: str = "rag_eval.thresholds/v1"
release_identity: Mapping[str, object] = field(default_factory=dict)
```

Set `DEFAULT_THRESHOLDS_PATH = Path("eval/rag_full_chain_thresholds.v2.json")`.

Add `--thresholds` to `preflight`, `sample`, and `run`, default it to `DEFAULT_THRESHOLDS_PATH`, pass it through to the existing loader, and record the loaded schema as `policy_version`. Do not add a second module entry point; keep `scripts/evaluate_rag_full_chain.py` as the supported CLI.

- [ ] **Step 5: Run Task 1 tests GREEN**

Expected: all selected tests pass and v1 remains loadable.

- [ ] **Step 6: Commit Task 1**

```powershell
git add eval/rag_full_chain_thresholds.v2.json src/rag_eval/contracts.py src/rag_eval/runner.py tests/test_rag_eval_contracts.py tests/test_rag_eval_runner.py
git commit -m "feat: add rag evaluation v2 policy"
```

---

### Task 2: Current Release Identity Resolver

**Files:**
- Create: `src/rag_eval/release.py`
- Create: `tests/test_rag_eval_release.py`

**Interfaces:**
- Consumes: `load_active_pointer`, `resolve_runtime_artifact_snapshot`, and config.
- Produces: `ReleaseIdentity`, `resolve_release_identity(cfg)`, and `validate_joint_health(identity, rag_health, wiki_health)`.

- [ ] **Step 1: Write failing resolver tests**

```python
def test_release_identity_matches_pointer_runtime_and_config(tmp_path: Path):
    pointer = _valid_pointer(generation=1, build="build-v3", collection="child-v3")
    cfg = _cfg(tmp_path, build="build-v3", collection="child-v3")
    identity = resolve_release_identity(
        cfg,
        pointer_loader=lambda _: pointer,
        snapshot_loader=lambda _: SimpleNamespace(build_version="build-v3"),
    )
    assert identity.generation == 1
    assert identity.build_version == "build-v3"
    assert identity.collection_name == "child-v3"


def test_release_identity_rejects_collection_drift(tmp_path: Path):
    pointer = _valid_pointer(generation=1, build="build-v3", collection="child-v3")
    cfg = _cfg(tmp_path, build="build-v3", collection="wrong")
    with pytest.raises(ReleaseIdentityError, match="collection"):
        resolve_release_identity(cfg, pointer_loader=lambda _: pointer, snapshot_loader=_snapshot)


def test_joint_health_requires_same_generation_build_and_schema():
    identity = _identity(generation=1, build_version="build-v3")
    rag = {"status": "ok", "provenance_status": "pass", "vectorstore_loaded": True}
    wiki = {"ready": True, "activationEpoch": 2, "buildVersion": "build-v3",
            "artifactSchemaVersion": "evb.media-asset/v3", "stale": False}
    with pytest.raises(ReleaseIdentityError, match="generation"):
        validate_joint_health(identity, rag, wiki)
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_release.py -q
```

- [ ] **Step 3: Implement immutable release identity**

```python
@dataclass(frozen=True)
class ReleaseIdentity:
    generation: int
    activation_id: str
    build_version: str
    artifact_schema_version: str
    collection_name: str
    build_manifest_sha256: str
    pointer_sha256: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)
```

`resolve_release_identity` must compare configured build/collection, active pointer, and runtime snapshot. `validate_joint_health` must require healthy RAG plus ready/non-stale Wiki with matching generation/build/schema. Accept Wiki generation from `activationEpoch` or `generation`.

- [ ] **Step 4: Run Task 2 tests GREEN**

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/rag_eval/release.py tests/test_rag_eval_release.py
git commit -m "feat: validate active rag release identity"
```

---

### Task 3: Metadata-Only Scoped MinIO Snapshot

**Files:**
- Create: `src/rag_eval/protected_minio.py`
- Create: `tests/test_rag_eval_protected_minio.py`
- Modify: `src/rag_eval/inventory.py:98-116, 463-535`

**Interfaces:**
- Consumes: runtime v3 media rows, `ReleaseIdentity`, MinIO `stat_object`.
- Produces: `ProtectedObjectRef`, `derive_protected_object_refs`, and `capture_scoped_minio_snapshot`.

- [ ] **Step 1: Write tests proving no bucket scan/body download**

```python
class MetadataOnlyClient:
    def __init__(self):
        self.stat_calls = []
    def stat_object(self, bucket, key):
        self.stat_calls.append((bucket, key))
        return SimpleNamespace(size=7, etag="etag-1", version_id="v1", metadata={
            "x-amz-meta-sha1": "1" * 40,
            "x-amz-meta-content-sha256": "2" * 64,
        })
    def list_objects(self, *args, **kwargs):
        raise AssertionError("must not list the bucket")
    def get_object(self, *args, **kwargs):
        raise AssertionError("must not download object bodies")


def test_scoped_snapshot_stats_only_referenced_objects():
    refs = (ProtectedObjectRef("assets", "reverse1999/a.png", 7, "2" * 64),)
    client = MetadataOnlyClient()
    snapshot = capture_scoped_minio_snapshot(client, refs)
    assert client.stat_calls == [("assets", "reverse1999/a.png")]
    assert snapshot["object_count"] == 1


def test_shared_resource_keeps_all_binding_authority():
    rows = [
        {"binding_id": "b1", "resource_id": "r1", "bucket": "assets", "object_key": "x.png", "size": 7, "sha256": "2" * 64},
        {"binding_id": "b2", "resource_id": "r1", "bucket": "assets", "object_key": "x.png", "size": 7, "sha256": "2" * 64},
    ]
    refs = derive_protected_object_refs(rows, default_bucket="assets")
    assert len(refs) == 1
    assert refs[0].binding_ids == ("b1", "b2")
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_protected_minio.py -q
```

- [ ] **Step 3: Implement exact-key snapshot**

```python
@dataclass(frozen=True, order=True)
class ProtectedObjectRef:
    bucket: str
    object_key: str
    size: int
    sha256: str
    binding_ids: tuple[str, ...] = ()
    resource_id: str = ""


def capture_scoped_minio_snapshot(client: object, refs: Sequence[ProtectedObjectRef]) -> dict[str, object]:
    objects = []
    for ref in sorted(refs):
        stat = client.stat_object(ref.bucket, ref.object_key)
        metadata = {str(k).lower(): str(v) for k, v in (stat.metadata or {}).items()}
        observed_sha256 = metadata.get("x-amz-meta-content-sha256") or metadata.get("sha256") or ref.sha256
        if ref.size >= 0 and int(stat.size) != ref.size:
            raise ProtectedMinioError("protected object size mismatch")
        if ref.sha256 and observed_sha256 != ref.sha256:
            raise ProtectedMinioError("protected object hash mismatch")
        objects.append({"bucket": ref.bucket, "object_key": ref.object_key,
                        "size": int(stat.size), "etag": str(stat.etag or "").strip('"'),
                        "version_id": stat.version_id, "sha256": observed_sha256,
                        "resource_id": ref.resource_id, "binding_ids": list(ref.binding_ids)})
    return {"schema_version": "rag_eval.scoped-minio-snapshot/v1",
            "object_count": len(objects), "objects": objects,
            "objects_sha256": _canonical_sha256(objects)}
```

Reject blank/unsafe keys and conflicting size/hash values for the same bucket/key. Missing metadata uses the hash-pinned manifest value; never download the body.

- [ ] **Step 4: Compose the scoped result into `ProtectedDataSnapshot`**

Add `release_identity` and the scoped MinIO payload to serialization and comparison. Keep injectable loaders for synthetic tests.

- [ ] **Step 5: Run Task 3 plus inventory tests GREEN**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_protected_minio.py tests/test_rag_eval_inventory.py -q
```

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/rag_eval/protected_minio.py src/rag_eval/inventory.py tests/test_rag_eval_protected_minio.py tests/test_rag_eval_inventory.py
git commit -m "feat: scope rag evaluation minio snapshots"
```

---

### Task 4: M1 Preflight Error Taxonomy and Release Gates

**Files:**
- Modify: `src/rag_eval/inventory.py:120-127, 686-760`
- Modify: `src/rag_eval/runner.py:94-173, 239-303`
- Test: `tests/test_rag_eval_inventory.py`
- Test: `tests/test_rag_eval_runner.py`

**Interfaces:**
- Consumes: release resolver, joint health, scoped snapshot, existing health/judge checks.
- Produces: `PreflightResult.release_identity` and stable M1 error codes.

- [ ] **Step 1: Write failing M1 classification tests**

```python
@pytest.mark.parametrize("error,code", [
    (MissingCredentialError("MINIO_ACCESS_KEY"), "READY.CREDENTIAL_MISSING"),
    (PermissionDeniedError("assets"), "READY.PERMISSION_DENIED"),
    (ReleaseIdentityError("generation mismatch"), "READY.RELEASE_IDENTITY_MISMATCH"),
    (ProtectedMinioError("metadata mismatch"), "READY.PROTECTED_SNAPSHOT_FAILED"),
])
def test_preflight_classifies_v2_failures(error, code):
    result = run_preflight(
        _cfg(), "http://backend", _judge_identity(),
        backend_health=lambda _: _healthy_rag(),
        wiki_health=lambda _: _healthy_wiki(),
        release_loader=lambda _: _identity(),
        inventory_loader=lambda _: _inventory(),
        snapshot_loader=lambda *_: (_ for _ in ()).throw(error),
    )
    assert result.allowed_to_run is False
    assert result.severity is Severity.SEV0
    assert result.events[0].event_code == code
```

Also assert missing credentials fail before MinIO client creation and failed preflight sends zero sampled requests.

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_inventory.py tests/test_rag_eval_runner.py -q
```

- [ ] **Step 3: Implement sanitized exception mapping**

```python
def _preflight_event_for(error: Exception) -> EvaluationEvent:
    if isinstance(error, MissingCredentialError):
        code, action = "READY.CREDENTIAL_MISSING", "configure read-only evaluation credentials"
    elif isinstance(error, PermissionDeniedError):
        code, action = "READY.PERMISSION_DENIED", "grant metadata read permission"
    elif isinstance(error, ReleaseIdentityError):
        code, action = "READY.RELEASE_IDENTITY_MISMATCH", "restore active release agreement"
    elif isinstance(error, ProtectedMinioError):
        code, action = "READY.PROTECTED_SNAPSHOT_FAILED", "repair protected object identity"
    else:
        code, action = "READY.DATA_UNAVAILABLE", "restore evaluation prerequisites"
    return EvaluationEvent.create(code, "M1", Severity.SEV0,
        observed={"error_type": type(error).__name__}, recommended_action=action)
```

Do not serialize raw messages that may contain credentials, paths, object keys, or SQL.

- [ ] **Step 4: Integrate release and Wiki health before sampling**

Resolve identity, fetch `/api/wiki/health`, validate joint health, capture scoped preflight snapshot, and return both identity and snapshot. Runner reuses that snapshot as before-state.

- [ ] **Step 5: Run Task 4 tests GREEN**

- [ ] **Step 6: Commit Task 4**

```powershell
git add src/rag_eval/inventory.py src/rag_eval/runner.py tests/test_rag_eval_inventory.py tests/test_rag_eval_runner.py
git commit -m "feat: classify rag evaluation release gates"
```

---

### Task 5: V2 Taxonomy, `udimo`, and Schema-Bound Sampling

**Files:**
- Create: `src/rag_eval/taxonomy.py`
- Create: `tests/test_rag_eval_taxonomy.py`
- Modify: `src/rag_eval/inventory.py:130-143, 147-219`
- Modify: `src/rag_eval/sampling.py:17-33, 213-265, 535-571`
- Modify: `eval/queries_core.jsonl`
- Test: `tests/test_rag_eval_sampling.py`
- Test: `tests/test_huiji_eval.py`

**Interfaces:**
- Consumes: policy version, artifact schema, current `CHARACTER_POLICIES`.
- Produces: `EvaluationTaxonomy`, `taxonomy_for_policy`, and a digest pinned into each v2 case.

- [ ] **Step 1: Write failing taxonomy tests**

```python
def test_v2_taxonomy_maps_item_to_collection_and_covers_udimo():
    taxonomy = taxonomy_for_policy("rag_eval.thresholds/v2", "evb.media-asset/v3")
    assert taxonomy.sections_for_intent("item") == ("collection",)
    assert "udimo" in taxonomy.p0_intents
    assert taxonomy.intents_for_section("collection") == ("item",)


def test_v2_manifest_pins_taxonomy_build_and_schema(inventory, thresholds_v2):
    cases = build_sample_manifest(inventory, thresholds_v2, 1999,
        build_version="crawler-v3-test", artifact_schema_version="evb.media-asset/v3")
    assert any("udimo" in case.expected_intents for case in cases)
    assert all(case.derivation["taxonomy_sha256"] for case in cases)
    assert all(case.derivation["build_version"] == "crawler-v3-test" for case in cases)


def test_smoke_item_uses_current_collection_section():
    row = next(row for row in iter_eval_rows(Path("eval/queries_core.jsonl"))
               if row["id"] == "item_sonetto")
    assert row["required_sections"] == ["collection"]
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_taxonomy.py tests/test_rag_eval_sampling.py tests/test_huiji_eval.py -q
```

- [ ] **Step 3: Implement immutable taxonomy**

```python
@dataclass(frozen=True)
class EvaluationTaxonomy:
    policy_version: str
    artifact_schema_version: str
    p0_intents: tuple[str, ...]
    intent_sections: Mapping[str, tuple[str, ...]]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_json())).hexdigest()

    def sections_for_intent(self, intent: str) -> tuple[str, ...]:
        return tuple(self.intent_sections.get(intent, ()))

    def intents_for_section(self, section: str) -> tuple[str, ...]:
        return tuple(i for i, sections in self.intent_sections.items() if section in sections)
```

Define v2 `item: ("collection",)` and `udimo: ("udimo",)`. Preserve a v1 adapter.

- [ ] **Step 4: Update inventory and sampling**

Pass taxonomy explicitly, add `"udimo": "尤提姆"` to labels, and pin policy/build/schema/taxonomy values in `EvalCase.derivation`. Validation rejects stale build/schema/taxonomy values.

- [ ] **Step 5: Update only the obsolete smoke expectation**

Change `item_sonetto.required_sections` from `["item"]` to `["collection"]`; keep every other field unchanged.

- [ ] **Step 6: Run Task 5 tests GREEN**

- [ ] **Step 7: Commit Task 5**

```powershell
git add src/rag_eval/taxonomy.py src/rag_eval/inventory.py src/rag_eval/sampling.py eval/queries_core.jsonl tests/test_rag_eval_taxonomy.py tests/test_rag_eval_sampling.py tests/test_huiji_eval.py
git commit -m "feat: align rag evaluation taxonomy with v3"
```

---

### Task 6: V3 Media Resource and Binding Gates

**Files:**
- Modify: `src/rag_eval/inventory.py:43-58, 221-258`
- Modify: `src/rag_eval/client.py` media normalization helpers
- Modify: `src/rag_eval/deterministic.py` media evaluation helpers
- Test: `tests/test_rag_eval_inventory.py`
- Test: `tests/test_rag_eval_client.py`
- Test: `tests/test_rag_eval_deterministic.py`

**Interfaces:**
- Consumes: v3 media rows and observed RAG/Wiki media payloads.
- Produces: binding/resource fields and stable M4 events.

- [ ] **Step 1: Write failing v3 media tests**

```python
def test_inventory_preserves_two_bindings_for_one_resource():
    rows = [
        _media_row(media_id="m1", resource_id="r1", binding_id="b1", child_id="c1"),
        _media_row(media_id="m1", resource_id="r1", binding_id="b2", child_id="c2"),
    ]
    inventory = build_inventory(_parents(), _children("c1", "c2"), rows, build_version="v3")
    assert {r.binding_id for r in inventory.media["m1"]} == {"b1", "b2"}
    assert {r.resource_id for r in inventory.media["m1"]} == {"r1"}


def test_media_gate_rejects_missing_binding_identity(v3_case, inventory):
    exchange = _exchange(media=[{"media_id": "m1", "resource_id": "r1", "binding_id": ""}])
    result = evaluate_deterministic(v3_case, exchange, inventory, _thresholds_v2())
    assert any(e.event_code == "MEDIA.BINDING_ID_MISSING" for e in result.events)


def test_media_gate_rejects_shared_resource_binding_loss(v3_case, inventory):
    exchange = _exchange(media=[{"media_id": "m1", "resource_id": "r1", "binding_id": "b1"}])
    result = evaluate_deterministic(v3_case, exchange, inventory, _thresholds_v2())
    assert any(e.event_code == "MEDIA.SHARED_BINDING_LOSS" for e in result.events)
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_inventory.py tests/test_rag_eval_client.py tests/test_rag_eval_deterministic.py -q
```

- [ ] **Step 3: Extend `MediaRecord` compatibly**

```python
binding_id: str = ""
resource_id: str = ""
object_key: str = ""
sha256: str = ""
size: int = -1
```

Populate from v3 rows. Client normalization accepts snake/camel case IDs and never transports object keys.

- [ ] **Step 4: Implement stable M4 events**

```text
MEDIA.BINDING_ID_MISSING      SEV-2
MEDIA.RESOURCE_ID_MISSING     SEV-2
MEDIA.BINDING_MISMATCH        SEV-1
MEDIA.SHARED_BINDING_LOSS     SEV-2
MEDIA.RELEASE_IDENTITY_DRIFT  SEV-1
```

Require v3 IDs only when active schema is `evb.media-asset/v3`.

- [ ] **Step 5: Run Task 6 tests GREEN**

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/rag_eval/inventory.py src/rag_eval/client.py src/rag_eval/deterministic.py tests/test_rag_eval_inventory.py tests/test_rag_eval_client.py tests/test_rag_eval_deterministic.py
git commit -m "feat: evaluate v3 media binding identity"
```

---

### Task 7: Consolidated V2 Metrics Document and Evaluation Report

**Files:**
- Create: `docs/evaluation/rag-full-chain-v2.md`
- Modify: `src/rag_eval/reporting.py`
- Create: `scripts/render_rag_evaluation_report.py`
- Modify test: `tests/test_rag_eval_reporting.py`

**Interfaces:**
- Consumes: `policy_version`, release identity, `preflight.json`, automatic summary, deterministic events, performance statistics, and optional human-review decisions.
- Produces: one stable metrics reference and one dated Markdown report without changing or deleting historical documents.

- [ ] **Step 1: Write failing report-content tests**

```python
def test_render_project_report_contains_all_required_sections(tmp_path):
    run_dir = _complete_run(tmp_path, human_review="pending")
    report = render_project_report(run_dir, metrics_doc_relative="../evaluation/rag-full-chain-v2.md")
    for heading in (
        "评估口径与版本",
        "发布身份",
        "M1 基础设施与快照",
        "M2 检索与引用",
        "M3 结构与生成",
        "M4 媒体资源与绑定",
        "M5 性能与稳定性",
        "D1-D4 阻断判定",
        "人工复核",
        "证据索引",
    ):
        assert heading in report


def test_pending_human_review_is_not_rendered_as_a_percentage(tmp_path):
    report = render_project_report(_complete_run(tmp_path, human_review="pending"))
    assert "等待人工复核" in report
    assert "人工通过率" not in report
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_reporting.py -q
```

- [ ] **Step 3: Write the consolidated v2 metrics document**

Include, in this order:

1. applicability and precedence over v1 for new runs;
2. immutable historical-file policy;
3. release-identity tuple and equality rules;
4. protected MinIO protocol and forbidden operations;
5. M1-M5 definitions, numerators, denominators, thresholds, and event mappings;
6. D1-D4 hard gates and severity meanings;
7. taxonomy v2 and v3 media-binding rules;
8. performance rebaseline status: keep existing thresholds until three comparable v2 runs exist;
9. automatic versus human-review boundaries;
10. evidence layout, rerun commands, and secret-redaction rules.

State explicitly that v1 remains at its current path as a historical artifact.

- [ ] **Step 4: Implement report rendering**

```python
def render_project_report(
    run_dir: Path,
    metrics_doc_relative: str = "../evaluation/rag-full-chain-v2.md",
) -> str:
    """Render a complete evaluation report from immutable run evidence."""
```

The renderer must:

- prefer `module_summary.final.v2.json` when it exists, otherwise use `module_summary.v2.json`;
- label every unavailable measurement as `未测`, `不适用`, or `等待人工复核`;
- never infer a human score from automatic checks;
- list sanitized error codes rather than exception text containing credentials;
- link evidence by repository-relative path;
- preserve full precision in JSON evidence and round only presentation values.

- [ ] **Step 5: Implement the create-new-only CLI**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe scripts\render_rag_evaluation_report.py --run-dir eval\rag_full_chain\20260723T120000Z --output docs\reports\2026-07-23-project-full-evaluation-v2.md --metrics-doc docs\evaluation\rag-full-chain-v2.md
```

Reject an existing output path unless `--force` is explicitly supplied. The real evaluation in Task 9 must not use `--force`.

- [ ] **Step 6: Run Task 7 tests GREEN**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_reporting.py -q
```

- [ ] **Step 7: Commit Task 7**

```powershell
git add docs/evaluation/rag-full-chain-v2.md src/rag_eval/reporting.py scripts/render_rag_evaluation_report.py tests/test_rag_eval_reporting.py
git commit -m "docs: consolidate rag evaluation v2"
```

---

### Task 8: Runner Integration, Regression Coverage, and Mutation Guard

**Files:**
- Modify: `src/rag_eval/runner.py`
- Modify: `src/rag_eval/reporting.py`
- Create: `docs/runbooks/rag-full-chain-evaluation.md`
- Test: `tests/test_rag_eval_runner.py`
- Test: `tests/test_rag_eval_reporting.py`

**Interfaces:**
- Consumes: all v2 components from Tasks 1-7.
- Produces: a deterministic run lifecycle with pre/post storage proof and a repeatable operator runbook.

- [ ] **Step 1: Write failing lifecycle and mutation-guard tests**

```python
def test_v2_runner_orders_release_preflight_sample_query_snapshot_report(mocker):
    calls = []
    runner = _runner_with_recording_dependencies(mocker, calls)
    runner.run()
    assert calls == [
        "resolve_release",
        "preflight",
        "sample",
        "query",
        "post_snapshot",
        "render_report",
    ]


def test_v2_runner_fails_when_protected_snapshot_changes(mocker):
    runner = _runner_with_snapshot_digests(mocker, before="aaa", after="bbb")
    result = runner.run()
    assert result.status == "blocked"
    assert any(e.event_code == "MINIO.PROTECTED_SNAPSHOT_CHANGED" for e in result.events)
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests/test_rag_eval_runner.py tests/test_rag_eval_reporting.py -q
```

- [ ] **Step 3: Integrate the v2 lifecycle**

Implement this exact order:

```text
resolve release identity
  -> protected MinIO preflight snapshot
  -> deterministic taxonomy-aware sampling
  -> read-only RAG/Wiki queries
  -> protected MinIO post snapshot
  -> automatic summary and consolidated report
```

If preflight fails, write sanitized preflight evidence and stop before sampling or querying. If the post snapshot differs, emit `MINIO.PROTECTED_SNAPSHOT_CHANGED` as SEV-0 and block the result.

- [ ] **Step 4: Update the operator runbook**

Document:

- process-local credentials only; never commit or print them;
- backend-only startup on port `18000`;
- no frontend process start, stop, build, test, or file modification;
- protected prefix metadata-only reads;
- 48-or-more-query minimum and deterministic seed;
- human-review finalization as a separate explicit step;
- backend shutdown and port verification;
- how to identify and preserve the dated report and immutable evidence.

- [ ] **Step 5: Run evaluator regression tests GREEN**

```powershell
$evaluatorTests = Get-ChildItem -LiteralPath tests -Filter 'test_rag_eval*.py' | Select-Object -ExpandProperty FullName
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest $evaluatorTests -q
```

- [ ] **Step 6: Run the complete Python suite GREEN**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests -q
```

- [ ] **Step 7: Verify source scope before committing**

```powershell
git status --short
git diff --name-only
git diff --check
```

The diff must not contain `frontend/`, `.worktrees/`, generated frontend assets, or storage data. Do not stage `.worktrees/`.

- [ ] **Step 8: Commit Task 8**

```powershell
git add src/rag_eval/runner.py src/rag_eval/reporting.py docs/runbooks/rag-full-chain-evaluation.md tests/test_rag_eval_runner.py tests/test_rag_eval_reporting.py
git commit -m "feat: integrate protected rag evaluation v2"
```

---

### Task 9: Execute the Real V2 Full Evaluation and Publish a New Historical Report

**Files:**
- Create: `docs/reports/2026-07-23-project-full-evaluation-v2.md`
- Preserve: every existing file under `docs/reports/` and `docs/evaluation/`
- Evidence only: a newly created directory under `eval/rag_full_chain/`

**Interfaces:**
- Consumes: the real backend, active release metadata, protected MinIO object metadata, and at least 48 generated evaluation cases.
- Produces: one evidence-backed dated report; automatic results remain distinct from any incomplete human audit.

- [ ] **Step 1: Confirm frontend-task isolation without touching it**

Use the Codex task-status tool to inspect task `019f8bae-73e7-7343-899b-42318370b0e9`. Record whether it is active or complete. Continue only in `D:\1999Wiki`; do not enter, edit, build, test, start, or stop `D:\1999Wiki\.worktrees\main-mobile-responsive`.

```powershell
git status --short
git diff --name-only
```

- [ ] **Step 2: Start only an isolated backend on port 18000**

Use a managed terminal session so it can be stopped reliably. Before startup, verify the port is free. Inject the operator-approved candidate MinIO credentials into that process only through the managed session's environment. Do not echo the values and do not write them to a file.

```powershell
Get-NetTCPConnection -LocalPort 18000 -State Listen -ErrorAction SilentlyContinue
if ([string]::IsNullOrWhiteSpace($env:MINIO_ACCESS_KEY)) { throw 'MINIO_ACCESS_KEY was not injected into this managed session.' }
if ([string]::IsNullOrWhiteSpace($env:MINIO_SECRET_KEY)) { throw 'MINIO_SECRET_KEY was not injected into this managed session.' }
D:\Anaconda32024\envs\1999wiki\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 18000
```

The variables exist only in the managed backend session and disappear when that session is stopped.

- [ ] **Step 3: Run strict v2 preflight**

```powershell
if ([string]::IsNullOrWhiteSpace($env:MINIO_ACCESS_KEY)) { throw 'MINIO_ACCESS_KEY was not injected into this evaluation session.' }
if ([string]::IsNullOrWhiteSpace($env:MINIO_SECRET_KEY)) { throw 'MINIO_SECRET_KEY was not injected into this evaluation session.' }
$preflightEvidence = Join-Path 'eval\rag_full_chain' ("preflight-v2-" + (Get-Date -Format 'yyyyMMddTHHmmssfff') + '.json')
D:\Anaconda32024\envs\1999wiki\python.exe scripts\evaluate_rag_full_chain.py preflight --base-url http://127.0.0.1:18000 --output $preflightEvidence --thresholds eval\rag_full_chain_thresholds.v2.json
Remove-Item Env:MINIO_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:MINIO_SECRET_KEY -ErrorAction SilentlyContinue
```

Proceed only if release identity matches across the repository, RAG, Wiki, and MinIO release marker and all protected metadata probes pass. A sanitized failure is a valid blocked outcome and must be reported honestly.

- [ ] **Step 4: Execute a deterministic 48-or-more-query run**

Capture the new run directory without guessing its timestamp:

```powershell
$beforeRuns = @(Get-ChildItem -LiteralPath eval\rag_full_chain -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
if ([string]::IsNullOrWhiteSpace($env:MINIO_ACCESS_KEY)) { throw 'MINIO_ACCESS_KEY was not injected into this evaluation session.' }
if ([string]::IsNullOrWhiteSpace($env:MINIO_SECRET_KEY)) { throw 'MINIO_SECRET_KEY was not injected into this evaluation session.' }
D:\Anaconda32024\envs\1999wiki\python.exe scripts\evaluate_rag_full_chain.py run --base-url http://127.0.0.1:18000 --seed 20260723 --output-root eval\rag_full_chain --thresholds eval\rag_full_chain_thresholds.v2.json
Remove-Item Env:MINIO_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:MINIO_SECRET_KEY -ErrorAction SilentlyContinue
$runDir = Get-ChildItem -LiteralPath eval\rag_full_chain -Directory | Where-Object { $_.FullName -notin $beforeRuns } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $runDir) { throw 'No new evaluation run directory was created.' }
```

Do not retry until a passing result appears. Every attempt remains evidence and must be referenced if it affects the conclusion.

- [ ] **Step 5: Handle human review without fabrication**

If a qualified reviewer has produced both required review files inside `$runDir`, validate and finalize them:

```powershell
$adjudicationResults = Join-Path $runDir 'adjudication_results.v2.jsonl'
$humanAuditResults = Join-Path $runDir 'human_audit_results.v1.jsonl'
if ((Test-Path -LiteralPath $adjudicationResults) -and (Test-Path -LiteralPath $humanAuditResults)) {
    D:\Anaconda32024\envs\1999wiki\python.exe scripts\evaluate_rag_full_chain.py finalize --run-dir $runDir --adjudication $adjudicationResults --human-audit $humanAuditResults
}
```

Otherwise, leave the human section as `等待人工复核`. Do not synthesize labels, pass rates, or reviewer identity.

- [ ] **Step 6: Render the new consolidated report**

```powershell
D:\Anaconda32024\envs\1999wiki\python.exe scripts\render_rag_evaluation_report.py --run-dir $runDir --output docs\reports\2026-07-23-project-full-evaluation-v2.md --metrics-doc docs\evaluation\rag-full-chain-v2.md
```

The report must distinguish `通过`, `不通过`, `阻断`, `未测`, `不适用`, and `等待人工复核`; include all automatic sample counts and denominators; explain any threshold retained pending rebaseline; and link the exact evidence directory.

- [ ] **Step 7: Stop the isolated backend and verify cleanup**

Stop the managed backend session, then verify no listener remains:

```powershell
Get-NetTCPConnection -LocalPort 18000 -State Listen -ErrorAction SilentlyContinue
```

The command must return no listener started by this task. Do not stop any frontend process.

- [ ] **Step 8: Run final verification**

```powershell
$evaluatorTests = Get-ChildItem -LiteralPath tests -Filter 'test_rag_eval*.py' | Select-Object -ExpandProperty FullName
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest $evaluatorTests -q
D:\Anaconda32024\envs\1999wiki\python.exe -m pytest tests -q
git diff --check
git status --short
git diff --name-only HEAD
```

Confirm the report exists, old reports remain unchanged, no frontend path appears in the diff, no credential value appears in tracked files, and the evidence run contains preflight, inventory/sample, raw query, automatic summary, and post-snapshot artifacts.

- [ ] **Step 9: Commit the report and any intentionally tracked evidence index**

```powershell
git add docs/reports/2026-07-23-project-full-evaluation-v2.md
git commit -m "docs: publish 2026-07-23 full evaluation"
```

Do not force-add ignored raw evidence, credentials, runtime logs, or generated frontend files.

---

## Completion Checklist

- [ ] `policy_version=v2` is explicit in every new evidence bundle and report.
- [ ] The release identity matches across repository, RAG, Wiki, and protected MinIO metadata or the run is blocked with a stable code.
- [ ] Protected MinIO checks use metadata-only reads and pre/post digest equality.
- [ ] The active inventory is release-scoped and does not traverse or download the entire bucket.
- [ ] Taxonomy v2 treats item intent as `collection` and covers `udimo`.
- [ ] V3 media checks preserve both resource and binding identity.
- [ ] At least 48 real queries were attempted after a successful strict preflight.
- [ ] Human-review status is honest and never inferred from automatic checks.
- [ ] M1-M5, D1-D4, severity, thresholds, denominators, and evidence links are consolidated in one new document.
- [ ] Existing metric and report files remain available as history.
- [ ] Evaluator tests and the complete Python suite pass after implementation.
- [ ] No frontend file, process, build artifact, or isolated frontend worktree was changed.
- [ ] No secret or MinIO credential was written to tracked files or evaluation evidence.
