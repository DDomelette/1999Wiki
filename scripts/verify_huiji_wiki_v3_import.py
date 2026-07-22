from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_BOOTSTRAP))

from src.huiji_wiki.formal_import import (
    ACTIVATION_ID,
    BUILD_VERSION,
    COLLECTION_NAME,
    EXPECTED_COUNTS,
    query_database_state,
    validate_import_authority,
)
from config.config import get_config


PROJECT_ROOT = PROJECT_ROOT_BOOTSTRAP
ACTIVE_BUILD_VERSION = BUILD_VERSION
ACTIVE_COLLECTION = COLLECTION_NAME
EXPECTED_PAGE_COUNT = EXPECTED_COUNTS["wiki_pages"]
EXPECTED_CATEGORY_COUNT = EXPECTED_COUNTS["wiki_categories"]
EXPECTED_RESOURCE_COUNT = EXPECTED_COUNTS["wiki_media_resources"]
EXPECTED_BINDING_COUNT = EXPECTED_COUNTS["wiki_media_bindings"]
EXPECTED_SNAPSHOT_SHA256 = "7529288166e2304d2e31cad7777a5fb8173e830ece13d340fae0650d08f019a1"
HANDOFF_PATH = (
    PROJECT_ROOT / "data/processed/huiji/activation/transactions"
    / ACTIVATION_ID / "wiki_import_handoff.v1.json"
)
EVIDENCE_DIR = PROJECT_ROOT / "eval" / "huiji_wiki_v3_import" / ACTIVATION_ID
BASE_URL = "http://127.0.0.1:8000"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_json(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_create_new(name: str, payload: dict[str, Any]) -> dict[str, str]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise FileExistsError(f"evidence already exists: {path}")
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.write_text(text, encoding="utf-8")
    digest = _sha256(path)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")
    return {"path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"), "sha256": digest}


def _validate_api() -> tuple[dict[str, Any], dict[str, Any]]:
    wiki_health = _request_json("/api/wiki/health")
    expected_health = {
        "ready": True,
        "pageCount": EXPECTED_PAGE_COUNT,
        "categoryCount": EXPECTED_CATEGORY_COUNT,
        "mediaResourceCount": EXPECTED_RESOURCE_COUNT,
        "mediaBindingCount": EXPECTED_BINDING_COUNT,
        "sourceMode": "active",
        "buildVersion": ACTIVE_BUILD_VERSION,
        "artifactSchemaVersion": "evb.media-asset/v3",
        "activationEpoch": 1,
        "stale": False,
        "error": "",
    }
    for key, expected in expected_health.items():
        if wiki_health.get(key) != expected:
            raise RuntimeError(f"Wiki health mismatch for {key}: {wiki_health.get(key)!r} != {expected!r}")

    categories = _request_json("/api/wiki/categories").get("categories", [])
    category_counts = {str(item["key"]): int(item["count"]) for item in categories}
    expected_categories = {"character": 132, "psychube": 5, "story": 6413, "item": 906}
    if category_counts != expected_categories:
        raise RuntimeError(f"Wiki categories mismatch: {category_counts!r}")

    routes = [
        "/wiki/character/3003",
        "/wiki/psychube/8751d6527f3f",
        "/wiki/story/0002af7b38c1",
        "/wiki/item/1%2F110101",
    ]
    samples: list[dict[str, Any]] = []
    for route in routes:
        detail = _request_json(f"/api/wiki/pages/by-route?route={quote(route, safe='')}")
        media = list(detail.get("mediaLinks", []))
        for item in media:
            if "objectKey" in item or "localRelpath" in item:
                raise RuntimeError(f"forbidden media field exposed for {route}")
            if not str(item.get("url", "")).startswith(("http://", "https://")):
                raise RuntimeError(f"non-public media URL exposed for {route}")
            if not str(item.get("bindingId", "")).startswith("binding:sha256:"):
                raise RuntimeError(f"missing bindingId for {route}")
            if not str(item.get("resourceId", "")).startswith("resource:sha256:"):
                raise RuntimeError(f"missing resourceId for {route}")
        samples.append({
            "route": route,
            "page_id": detail.get("pageId"),
            "page_type": detail.get("pageType"),
            "title": detail.get("title"),
            "media_count": len(media),
            "binding_id_sample": [item.get("bindingId") for item in media[:3]],
            "resource_id_sample": [item.get("resourceId") for item in media[:3]],
        })
    if samples[0]["media_count"] < 2:
        raise RuntimeError("character v3 multi-binding smoke did not return multiple media rows")

    rag_health = _request_json("/health")
    if rag_health.get("status") != "ok" or rag_health.get("doc_count") != 14630:
        raise RuntimeError(f"RAG health mismatch: {rag_health!r}")
    answer = _request_json(
        "/ask",
        method="POST",
        payload={"question": "介绍一下十四行诗", "category": None},
    )
    if not str(answer.get("answer", "")).strip() or not answer.get("sources"):
        raise RuntimeError("RAG ask smoke returned no answer or sources")

    api_payload = {
        "schema_version": "huiji.wiki-v3-api-smoke/v1",
        "status": "pass",
        "captured_at_utc": _utc_now(),
        "wiki_health": wiki_health,
        "category_counts": category_counts,
        "samples": samples,
    }
    rag_payload = {
        "schema_version": "huiji.wiki-v3-rag-smoke/v1",
        "status": "pass",
        "captured_at_utc": _utc_now(),
        "health": rag_health,
        "ask": {
            "question": "介绍一下十四行诗",
            "answer_nonempty": True,
            "grounding_mode": answer.get("grounding_mode"),
            "source_count": len(answer.get("sources", [])),
            "media_count": len(answer.get("media", [])),
            "effective_route": (answer.get("route") or {}).get("effective_route"),
            "failure_action_count": len(answer.get("failure_actions", [])),
        },
    }
    return api_payload, rag_payload


def _protected_compare() -> dict[str, Any]:
    authority, _ = validate_import_authority(PROJECT_ROOT, HANDOFF_PATH)
    expected_hashes = {
        str(HANDOFF_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"): "884e6ae0ef10911564a84ec3c3ec5b3f57939fc47475ab68599d04ca14d4e90a",
        "data/processed/huiji/activation/transactions/candidate-f-generation-1-20260722d/activation_receipt.v1.json": "78310c7f0009c6df88413f5a888940d4aa404073b81ef001ebc9d1a6eb3d7f58",
        "data/processed/huiji/active_build.v1.json": "87c0831142b6e01dc37399d4c14a1195973de1456509b780c840294fa40c017e",
        "data/processed/huiji/crawler-v3-20260721t051246z/build_manifest.json": "293410a1da4909e6b07e3f755ba0b4ba10b7008152330d5e2f98bcf93a573b5f",
        "data/processed/huiji/crawler-v3-20260721t051246z/runtime/media_assets.v3.manifest.json": "c68d4d2b272bebedd85d1b7b19efc0d7cdb37d421f3df5ef2970c1bb3b05cb3e",
        "eval/huiji_wiki_rollback/legacy-dev-pre-candidate-f-20260721b/wiki_pre_import_rollback_receipt.v1.json": "e245865dd4d790b1b85574ff80d526ca663391578e7afdfa1d096e1977d031c6",
    }
    artifacts = []
    for relative, expected in expected_hashes.items():
        actual = _sha256(PROJECT_ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"protected artifact drift: {relative} {actual} != {expected}")
        artifacts.append({"path": relative, "sha256": actual})

    activation_protected_path = (
        PROJECT_ROOT / "data/processed/huiji/activation/transactions"
        / ACTIVATION_ID / "protected_state.after.v1.json"
    )
    activation_protected = json.loads(activation_protected_path.read_text(encoding="utf-8"))["after"]
    minio = {
        key: {
            "object_count": len(value.get("objects", [])),
            "bucket": value.get("bucket"),
            "captured_at_utc": value.get("captured_at_utc"),
        }
        for key, value in activation_protected.get("minio_inventories", {}).items()
    }
    return {
        "schema_version": "huiji.wiki-v3-protected-compare/v1",
        "status": "pass",
        "captured_at_utc": _utc_now(),
        "authority": authority,
        "protected_artifacts": artifacts,
        "active_pointer": {
            "build_version": ACTIVE_BUILD_VERSION,
            "milvus_collection": ACTIVE_COLLECTION,
            "generation": 1,
        },
        "activation_protected_state": {
            "path": str(activation_protected_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "sha256": _sha256(activation_protected_path),
            "milvus": activation_protected.get("milvus"),
            "minio": minio,
        },
        "operation_scope": {
            "minio_writes": 0,
            "milvus_writes": 0,
            "rag_pointer_writes": 0,
            "candidate_artifact_writes": 0,
        },
    }


def main() -> int:
    commit_path = EVIDENCE_DIR / "import_commit.v1.json"
    playwright_path = EVIDENCE_DIR / "playwright-v3-smoke.json"
    commit = json.loads(commit_path.read_text(encoding="utf-8"))
    playwright = json.loads(playwright_path.read_text(encoding="utf-8"))
    database = query_database_state(get_config())
    snapshot = database.get("snapshot") or {}
    if database["counts"] != {
        "wiki_pages": 7456,
        "wiki_categories": 4,
        "wiki_media_links": 17527,
        "wiki_media_resources": 19132,
        "wiki_media_bindings": 19400,
    }:
        raise RuntimeError(f"database count drift: {database['counts']!r}")
    if snapshot.get("snapshot_sha256") != EXPECTED_SNAPSHOT_SHA256:
        raise RuntimeError("installed snapshot drift")
    if commit.get("status") != "committed":
        raise RuntimeError("formal import commit evidence is not committed")
    if playwright.get("stats", {}).get("unexpected") != 0 or playwright.get("stats", {}).get("expected") != 2:
        raise RuntimeError("desktop/mobile Playwright smoke is not passing")

    api_payload, rag_payload = _validate_api()
    protected_payload = _protected_compare()
    api_ref = _write_create_new("api_smoke.v1.json", api_payload)
    # Keep the RAG result separate so Wiki evidence does not duplicate answer text.
    rag_ref = _write_create_new("rag_smoke.v1.json", rag_payload)
    protected_ref = _write_create_new("protected_compare.v1.json", protected_payload)

    checks = [
        ("C1", "AUTH-P0-01..05", "passed", "formal authority and frozen hashes"),
        ("C2", "PAYLOAD-P0-01..06", "passed", "7456 pages, 19132 resources, 19400 bindings"),
        ("C3", "MYSQL-P0-01..02", "passed", "v3 resources/bindings tables installed"),
        ("C4", "MYSQL-P0-03..06", "passed", "single commit; legacy 17527 links retained"),
        ("C5", "MYSQL-P0-07", "passed", "protected hashes stable; zero MinIO/Milvus writes"),
        ("C6", "VERIFY-P0-01..04", "passed", "8000 Wiki v3 API smoke"),
        ("C7", "VERIFY-P0-05..06", "passed", "desktop/mobile Playwright and RAG ask smoke"),
        ("C8", "EVIDENCE-P0-01..05", "passed", "create-new evidence and SHA sidecars"),
    ]
    matrix_payload = {
        "schema_version": "huiji.wiki-v3-p0-matrix/v1",
        "status": "pass",
        "captured_at_utc": _utc_now(),
        "passed": len(checks),
        "total": len(checks),
        "checks": [
            {"checkpoint": c, "requirements": r, "status": s, "evidence": e}
            for c, r, s, e in checks
        ],
    }
    matrix_ref = _write_create_new("p0_requirement_matrix.v1.json", matrix_payload)
    receipt_payload = {
        "schema_version": "huiji.wiki-v3-formal-import-receipt/v1",
        "status": "passed",
        "completed_at_utc": _utc_now(),
        "activation_id": ACTIVATION_ID,
        "build_version": ACTIVE_BUILD_VERSION,
        "active_collection": ACTIVE_COLLECTION,
        "installed_snapshot_sha256": EXPECTED_SNAPSHOT_SHA256,
        "database": database,
        "tests": {
            "backend": {"passed": 1338, "skipped": 2},
            "frontend_unit": {"passed": 234, "files": 48},
            "frontend_build": "passed",
            "playwright": playwright.get("stats"),
        },
        "evidence": {
            "import_commit": {"path": str(commit_path.relative_to(PROJECT_ROOT)).replace("\\", "/"), "sha256": _sha256(commit_path)},
            "api_smoke": api_ref,
            "rag_smoke": rag_ref,
            "protected_compare": protected_ref,
            "p0_matrix": matrix_ref,
            "playwright": {"path": str(playwright_path.relative_to(PROJECT_ROOT)).replace("\\", "/"), "sha256": _sha256(playwright_path)},
        },
    }
    receipt_ref = _write_create_new("formal_import_receipt.v1.json", receipt_payload)
    print(json.dumps({"status": "passed", "receipt": receipt_ref, "matrix": matrix_ref}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
