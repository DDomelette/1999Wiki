"""Build a hash-pinned Wiki compatibility receipt from the shared RAG fixture."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.huiji_wiki.media_v3 import normalize_media_v3_rows


RECEIPT_SCHEMA = "huiji.wiki-media-v3-compatibility-receipt/v1"
FIXTURE_RELATIVE_ROOT = Path("tests/fixtures/contracts/huiji_media_v3")
FIXTURE_NAMES = (
    "media_assets.v3.schema.json",
    "media_assets.v3.jsonl",
    "expected_resources.json",
    "expected_bindings.json",
)


def evaluate_shared_fixture(project_root: Path) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    fixture_root = project_root / FIXTURE_RELATIVE_ROOT
    paths = {name: fixture_root / name for name in FIXTURE_NAMES}
    missing = [name for name, path in paths.items() if not path.is_file()]
    base: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "blocked_shared_fixture_missing" if missing else "checking",
        "fixture_root": FIXTURE_RELATIVE_ROOT.as_posix(),
        "fixtures": [],
    }
    if missing:
        base["missing"] = sorted(missing)
        return base

    schema_document = _load_json(paths["media_assets.v3.schema.json"])
    if schema_document.get("schema_version") != "evb.media-assets/v3":
        return {**base, "status": "blocked_schema_mismatch", "error": "media v3 schema label mismatch"}

    rows = _load_jsonl(paths["media_assets.v3.jsonl"])
    try:
        resources, bindings, _links = normalize_media_v3_rows(
            (str(row["owner_page_id"]), row) for row in rows
        )
    except (KeyError, ValueError) as exc:
        return {**base, "status": "blocked_contract_validation_failed", "error": str(exc)}

    expected_resources = _load_json(paths["expected_resources.json"])
    expected_bindings = _load_json(paths["expected_bindings.json"])
    actual_resource_ids = {row["resource_id"] for row in resources}
    actual_binding_ids = {row["binding_id"] for row in bindings}
    resource_error = _compare_expected_identity(
        expected_resources, actual_resource_ids, "resource_id", "resources"
    )
    binding_error = _compare_expected_identity(
        expected_bindings, actual_binding_ids, "binding_id", "bindings"
    )
    if resource_error or binding_error:
        return {
            **base,
            "status": "blocked_expected_projection_mismatch",
            "errors": [error for error in (resource_error, binding_error) if error],
        }

    bindings_per_resource: dict[str, int] = {}
    for binding in bindings:
        resource_id = binding["resource_id"]
        bindings_per_resource[resource_id] = bindings_per_resource.get(resource_id, 0) + 1
    shared_groups = sorted(
        resource_id for resource_id, count in bindings_per_resource.items() if count > 1
    )
    if not shared_groups:
        return {
            **base,
            "status": "blocked_multibinding_fixture_missing",
            "error": "shared fixture must contain resource-to-many-binding evidence",
        }

    base.update({
        "status": "passed",
        "fixtures": [
            {
                "path": (FIXTURE_RELATIVE_ROOT / name).as_posix(),
                "sha256": _sha256(path),
            }
            for name, path in paths.items()
        ],
        "input_binding_count": len(rows),
        "unique_binding_count": len(actual_binding_ids),
        "resource_count": len(actual_resource_ids),
        "resource_to_many_binding_count": len(shared_groups),
        "resource_to_many_binding_ids": shared_groups,
        "legacy_v2_supported": True,
        "media_v3_supported": True,
    })
    if base["input_binding_count"] != base["unique_binding_count"]:
        base["status"] = "blocked_duplicate_binding_identity"
    return base


def write_passing_receipt(project_root: Path, output_path: Path) -> dict[str, Any]:
    payload = evaluate_shared_fixture(project_root)
    if payload["status"] != "passed":
        return payload
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"compatibility receipt already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _compare_expected_identity(
    payload: Any,
    actual_ids: set[str],
    id_field: str,
    collection_name: str,
) -> str:
    expected_ids, expected_count = _expected_identity(payload, id_field, collection_name)
    if expected_count is not None and expected_count != len(actual_ids):
        return f"{collection_name} count mismatch: expected {expected_count}, got {len(actual_ids)}"
    if expected_ids is not None and expected_ids != actual_ids:
        return f"{collection_name} identity set mismatch"
    return ""


def _expected_identity(
    payload: Any,
    id_field: str,
    collection_name: str,
) -> tuple[set[str] | None, int | None]:
    value = payload
    count: int | None = None
    if isinstance(payload, dict):
        raw_count = payload.get("count") or payload.get(f"{collection_name}_count")
        if isinstance(raw_count, int):
            count = raw_count
        for key in (collection_name, "items", "rows", "ids"):
            if key in payload:
                value = payload[key]
                break
        else:
            if payload and all(isinstance(key, str) for key in payload):
                return set(payload), count if count is not None else len(payload)
    if not isinstance(value, list):
        return None, count
    ids: set[str] = set()
    for item in value:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, dict) and item.get(id_field):
            ids.add(str(item[id_field]))
    return ids, count if count is not None else len(value)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("media v3 fixture row must be an object")
                result.append(value)
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
