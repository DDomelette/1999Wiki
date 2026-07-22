from __future__ import annotations

from pathlib import Path

import pytest

from src.huiji_wiki.formal_import import (
    EXPECTED_COUNTS,
    validate_import_authority,
    validate_payload,
)
from src.huiji_wiki.importer import WikiImportPayload


def _payload() -> WikiImportPayload:
    pages = [
        {"page_id": f"page:{index}", "route": f"/wiki/page/{index}"}
        for index in range(EXPECTED_COUNTS["wiki_pages"])
    ]
    resources = [
        {"resource_id": f"resource:{index}"}
        for index in range(EXPECTED_COUNTS["wiki_media_resources"])
    ]
    bindings = [
        {
            "binding_id": f"binding:{index}",
            "resource_id": f"resource:{index % len(resources)}",
            "page_id": f"page:{index % len(pages)}",
        }
        for index in range(EXPECTED_COUNTS["wiki_media_bindings"])
    ]
    return WikiImportPayload(
        pages=pages,
        categories={f"category:{index}": {} for index in range(EXPECTED_COUNTS["wiki_categories"])},
        media_links=[],
        media_resources=resources,
        media_bindings=bindings,
        snapshot=object(),  # type: ignore[arg-type]
        full_replace=True,
    )


def test_validate_payload_preserves_all_bindings_and_checks_closure():
    payload = _payload()

    counts = validate_payload(payload)

    assert counts["wiki_media_resources"] == 19132
    assert counts["wiki_media_bindings"] == 19400

    payload.media_bindings[-1]["resource_id"] = "resource:missing"
    with pytest.raises(ValueError, match="missing resource"):
        validate_payload(payload)


def test_validate_payload_rejects_duplicate_binding_identity():
    payload = _payload()
    payload.media_bindings[-1]["binding_id"] = payload.media_bindings[0]["binding_id"]

    with pytest.raises(ValueError, match="duplicate binding_id"):
        validate_payload(payload)


def test_authority_rejects_handoff_hash_before_loading_contract(tmp_path: Path):
    handoff = tmp_path / "wiki_import_handoff.v1.json"
    handoff.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="handoff file hash mismatch"):
        validate_import_authority(
            tmp_path,
            handoff,
            expected_handoff_sha256="0" * 64,
        )

